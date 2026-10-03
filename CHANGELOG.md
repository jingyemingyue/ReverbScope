# Changelog

All notable changes to RoomScope are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). How a version is cut is in
`docs/RELEASE_PLAN.md`.

## [Unreleased]

### Added
- **Two download betas.** The README and installation pages offer a
  **stable beta** (fewer bugs, narrower feature set: last published
  pre-release `0.5.0b1`) and a **preview beta** (stronger features, may
  be unstable: this development line). Both are still beta. No GitHub
  Release was published for the preview track.
- **Docs site SEO files.** `scripts/build_docs_site.py` writes a title,
  meta description, canonical URL, and Open Graph title/description on
  every page, plus `sitemap.xml` and a `robots.txt` that allows
  indexing. Descriptions skip language switchers and download-URL lines
  so the hub and install pages get a real search snippet. No public
  docs host is configured; URLs use the placeholder
  `https://docs.example.invalid/roomscope/` until `--base-url` is set.
  This change does not submit the site to Google.
- **Follow the DAW in play.** The sweep sample rate is the only session
  setting RoomScope already treats as DAW-dependent; it must match the
  chosen project. `roomscope daw` lists declared / fake projects (this
  VM has no DAW and does not query hosts). Zero or several candidates
  raise an ask (`DawChoiceNeeded`); RoomScope does not guess. CLI:
  `roomscope sweep --follow-daw --daw NAME [--daw-project TITLE]`.
  GUI Universal DAW Mode: **Choose DAW to follow...** before Save Test
  Signal. Fake path: `ROOMSCOPE_FAKE_DAWS=Name:rate[:project]`,
  `;`-separated. A plain `roomscope sweep --out` still uses 48 kHz so
  existing goldens stay valid. No real DAW was running.
- **Imported room scan.** `roomscope analyze --scan FILE` (and the
  Placement page) reads an ASCII PLY point cloud or Wavefront OBJ the
  user already has. Coordinates stay in file units, treated as metres,
  and are drawn as faint points on the placement picture. Binary PLY is
  refused. RoomScope does not talk to a lidar; the checked-in sample is
  `tests/fixtures/synthetic_room.ply` (a 4×3×2.5 m shoebox, not a
  capture). Formats: Stanford Triangle Format / Greg Turk
  (http://paulbourke.net/dataformats/ply/) and Library of Congress
  FDD000507 (Wavefront OBJ). Clean-room readers; no Open3D, trimesh or
  CloudCompare source.
- **Impulse-response spectrum.** `analyze` and `analyze-ir` now store a
  Welch (1967) PSD of the deconvolved IR (`core/spectrum.py`), with the
  same AES17 density scaling as the noise tab (`10*log10(2*psd)`). It is
  a separate tab and `spectrum.csv`, not a gated frequency response and
  not a quiet-segment noise PSD. Shown on the synthetic path and the
  fake backend; this VM has no analyser and no claim of one.
- **Referenced interface specs.** `roomscope devices --referenced` and the
  inventory JSON `referenced` object cite PortAudio v19.7.0 compiled
  defaults (including the OSS 4×128-frame request), alsa-lib dmix
  48 kHz / 2 ch, PipeWire `default.clock.rate` 48 kHz, Focusrite Scarlett
  2i2 / 18i20 4th Gen user-guide figures, and the RME Babyface Pro FS
  product page. Empty cells stay empty when the source does not state a
  number. None of this is a HARDWARE_TESTS.md PASS.
- **Device capability catalog.** `roomscope devices --json` and
  `roomscope doctor` now always include RoomScope's six measurement rates
  (`SUPPORTED_SAMPLE_RATES`) and a host-API catalog built from
  `HOST_API_KINDS`, `HOST_API_PREFERENCE`, `HOST_API_NOTES` and PortAudio's
  documented default latencies. The fake backend advertises 8 inputs, 2
  outputs and those six rates without a PortAudio probe. A machine with no
  audio devices still reports the catalog; its device list stays empty.
  Standalone sessions store the same parameters in `audio_interface` and
  `bit_depth` (`32-bit float`). This is not a hardware-matrix result.
- **GUI and CLI languages.** Besides English and Simplified Chinese, the
  interface catalogs now include Traditional Chinese, Japanese, Korean,
  Spanish, French and German (`--lang zh_TW` / `ja` / `ko` / `es` / `fr` /
  `de`, and Settings → Language). License and legal sentences stay in
  English. User-facing docs remain English and Simplified Chinese.

### Changed
- **Placement picture shows the first-order image source.** When the
  vertical axis is solved, the rotatable 3D schematic draws the hollow
  image of the loudspeaker through the plane above and the dashed
  specular bounce, the way pyroomacoustics' documented `Room.plot`
  shows sources, microphones and images. The construction is
  Allen & Berkley (1979), implemented clean-room in
  `horizontal_plane_image_path` (CODE_PROVENANCE.md). No wall or room
  is invented; the measurement steps are unchanged.
- **Desktop chrome.** Shared page margins, form column alignment, card
  padding, and a slightly larger type scale so Home, measure, results and
  compare line up. The measurement steps are unchanged.
- **Chu noise-power subtraction on the Schroeder integral.** After Lundeby
  finds a floor, RoomScope subtracts that mean-square estimate from `h²`
  (clipping negatives) before backward integration and the early/late
  energy sums. The idea is Chu (1978), combined with the existing Lundeby
  truncation the way pyrato documents `energy_decay_curve_chu_lundeby`;
  the step is a clean-room reimplementation (CODE_PROVENANCE.md).
  `AnalysisSettings.decay_subtract_noise` (default on) turns it off.
  On a 0.5 s exponential plus a −50 dB floor (48 kHz, 2 s, seed 11):
  Lundeby-only T30 0.5485 s → Chu–Lundeby 0.5404 s (true 0.500;
  error 9.7 % → 8.1 %, a 17 % relative error cut). A clean alternating
  exponential stays within 0.04 % (0.500000 → 0.499813 s). Broadband
  `analyze_band` on that noisy IR: 1.80 ms → 2.03 ms. The settling-cache
  path is unchanged.
- **Noise-band filter settling.** `settling_samples` grows a short impulse
  until the unused tail is below the 0.001 energy remainder, then caches
  the length. Octave-band results match a full 4 s impulse. On this Linux
  VM the old 4 s impulse took 1.24 s for eight bands × three repeats;
  the new length is cached after 0.002 s. A 2 s synthetic `analyze` that
  measures octave-band noise fell from 0.54 s to 0.13 s (4×); broadband
  T30 and the eight band levels were identical.

## [0.5.0b1] - 2026-10-01

Software beta 1. This is **not** 0.5.0: the release plan's 0.5.0 still
requires a dated hardware-matrix PASS, and none exists. No signed bundles,
no PyPI upload, and no claim that a real interface or DAW has been measured.
What this beta adds on top of 0.4.1 is the rest of the single-microphone
algorithm the methodology already allowed, and the desktop presentation of it.

### Added
- **Early and late energy.** Each band now reports ISO 3382-1 clarity,
  definition and centre time from the same noise truncation as the decay:
  C50 (50 ms, speech), C80 (80 ms, music), D50 (percent of energy in the
  first 50 ms) and centre time. A ratio is withheld below 20 dB of decay
  range. They are not a room score, not STI, and not spatially averaged.
  The command line, the results page and `energy_metrics.csv` show them.
  A comparison differenced the broadband values only when both sides are
  valid.
- **Clarity advice follows the recording profile.** A profile may add one
  notice when broadband C50 or C80 is a poor fit for that kind of recording
  (voice-over is the strictest; drums do not judge clarity; a room microphone
  is flagged when the ratio is too dry, not when it is low). The threshold
  is an engineering choice, stated in the finding, and the sentence says it
  is one position, not a room grade. An invalid ratio produces no notice.
  The "Clarity" line in "At a glance" uses the same conclusion.

### Changed
- **Command line.** Root `--help`, subcommand descriptions and the epilog wrap
  on a narrow terminal (they ran past 60 columns). `roomscope demo` clears its
  progress line with spaces, not `ESC[2K`, so `--color never` and `NO_COLOR`
  stay free of escape sequences. Next-step commands quote a path that contains
  a space. `sweep`, `export` and `show --list` say so when `--format json` does
  not apply instead of ignoring it. On a narrow encoding (`cp1252`), signs such
  as `Δ` are widened before the line is wrapped, so a demo line no longer runs
  past the terminal. On Windows a next-step path is printed with slashes, so
  the same line pastes into cmd, PowerShell and Git Bash; a space is still
  quoted, and a POSIX shell still quotes a backslash.
- **Desktop app.** The home screen shows which keyboard shortcut opens each
  mode: ⌃1 / ⌃2 / ⌃3 (⌘1 / ⌘2 / ⌘3 on macOS), the same keys as the Measure
  menu. A status bar names the version and the current page. Results can
  copy the full text report to the clipboard. An unexpected failure is
  explained in the interface language (the traceback goes to the log, not
  the dialog); the text can be selected and copied. The two-clock warning
  uses translated buttons and does not measure unless you ask it to. The
  About box is translated. Shortcut marks fit their badges. Section headings
  are not letter-spaced, so Chinese is not spread out. Reports use a font
  that can draw Chinese. The tape-measure form and the Placement page show a
  rotatable picture of the microphone, the loudspeaker and the two tapes.
  When a measurement solves the vertical axis, a ring marks every loudspeaker
  position that result allows. The picture does not draw a room or a wall.

## [0.4.1] - 2026-09-29

The first public pre-release, for early testers (0.4.0 was never tagged,
because #17 had to be fixed before any bundle is published, RELEASE_PLAN.md
§4). Every platform gets two downloads, a **Desktop Edition** (GUI and
command line) and a **Terminal Edition** (command line only, built without
Qt); `roomscope demo` tries the whole workflow without an interface; the
command line has one presentation layer (home screen, "At a glance"
reports, numbered next steps, one error block, help in workflow order), in
English and Simplified Chinese. It closes the review follow-ups #9–#17, each
with a synthetic test that fails on 0.4.0; makes the bundles and the DAW
workflow usable by someone other than the maintainer; and adds what the
software-readiness phase needs before community hardware tests
(RELEASE_PLAN.md §2): the audio device inventory and pre-flight,
`roomscope doctor` and the environment report, the GUI redesign, and issue
templates for hardware and DAW reports. Run-time dependency floor:
**matplotlib ≥ 3.10** (was ≥ 3.8). Still no hardware or DAW result: every
cell of the hardware and DAW matrices stays *Not tested* until a community
report fills it. The bundles are not signed for distribution (macOS: ad hoc,
not notarized; Windows: no Authenticode), and nothing is on PyPI.

### Added
- **Desktop Edition and Terminal Edition.** Every platform now has two
  downloads, named for edition, system and CPU:
  `RoomScope-Desktop-macOS-arm64.dmg`, `RoomScope-Desktop-macOS-x86_64.dmg`,
  `RoomScope-Desktop-Windows-x64-Setup.exe`, `RoomScope-Desktop-Windows-x64.zip`,
  `RoomScope-Desktop-Linux-x86_64.tar.gz` (GUI and command line), and
  `RoomScope-Terminal-macOS-arm64.tar.gz`, `RoomScope-Terminal-macOS-x86_64.tar.gz`,
  `RoomScope-Terminal-Windows-x64.zip`, `RoomScope-Terminal-Linux-x86_64.tar.gz`
  (command line only). The Terminal Edition is built by the same release job
  without Qt, PySide6 and matplotlib (about 60 MB against 150 MB on Linux);
  `check_bundle_contents.py --terminal` fails a build that still contains
  them, and `smoke_bundle.py --terminal` runs the demo in English and
  Chinese, checks that `--format json` prints only JSON and that
  `roomscope gui` answers *This is the Terminal Edition of RoomScope. Install
  the Desktop Edition to use the GUI.* (in Chinese too) instead of a
  traceback. Both smokes check the edition and the CPU architecture the
  bundle reports; the Windows installer smoke also checks the Start menu
  entry and that uninstalling removes it. The Windows Terminal Edition has a
  `RoomScope Terminal.cmd` that opens a Command Prompt in its folder.
- **`roomscope demo`**: try the whole workflow without an interface or a
  microphone. It writes a sweep, simulates two microphone positions in a
  made-up room (a desk reflection at one, a 110 Hz room mode at both, mains
  hum), analyses and compares them with the real pipeline, and ends with
  numbered next steps. The terminal says first that the data is synthetic;
  every session it saves has the mode `synthetic_demo` and a note saying so;
  it never overwrites a folder it did not write. Works on a CLI-only install.
- **Home screen**: bare `roomscope` shows the version, one sentence and the
  three commands to start from instead of argparse's error (still exit
  code 2, on stderr).
- **Next steps** after `sweep`, after `analyze` / `measure` with `--out`, and
  after the demo: numbered, with commands that can be copied whole.
- **Command-line presentation.** `roomscope analyze`, `show`, `compare`,
  `doctor`, `devices`, `sweep` and `measure` print sectioned reports with
  aligned fields and tables, a summary of the broadband results, and a
  symbol and a word with every status (`✓` / `!` / `×`; `[OK]` / `[WARN]` /
  `[ERROR]` where the terminal cannot show them). Widths are display widths,
  so Chinese tables line up; long notes wrap under themselves (paths and URLs
  are never split, so they can be copied); a table that
  does not fit a narrow terminal becomes one block per row. `measure` shows
  the devices, channels and rate it will use and the pre-flight checks that
  passed before anything plays, then one progress line (redrawn on a
  terminal; a single stage line in a log file) instead of about seventy
  percentage lines. Errors say when nothing was played. `--help` groups the
  commands and gives a few examples. New global option
  `--color auto|always|never`; `NO_COLOR` and `TERM=dumb` are honoured; pipes
  and files never receive escape sequences. One internal renderer
  (`cli/console.py`, standard library only); no new dependency. JSON output,
  schemas, stored files and exit codes are unchanged; the GUI's *Full report*
  panes show the same layout (see Changed).
- **Simplified Chinese throughout.** Everything a user reads can be in
  Simplified Chinese: the GUI (Qt's own buttons and dialogs too, from Qt's
  `qtbase` catalog), every CLI help screen and argparse's usage and error
  texts, the text reports, the environment report, the Device Inspector,
  chart titles, axes and legends (CJK font fallback in every chart), the
  Windows installer and uninstaller (Simplified Chinese chosen from the
  Windows display language; released Inno Setup up to 6.7 does not install
  its Chinese messages, so the build fetches the maintained
  `ChineseSimplified.isl` from the Inno Setup repository at tag `is-6_7_1`
  and checks its SHA-256, `scripts/inno_chinese_messages.py`), `README.zh-CN.md`,
  `SECURITY.zh-CN.md`, `docs/HARDWARE_TESTS.zh-CN.md`, a Chinese docs index,
  and Chinese GitHub issue forms for bug, measurement, interface test, DAW
  report and feature request with the same fields, evidence rules and
  privacy notes as the English ones. Result files do not change: notes,
  warnings and reasons stay English in `result.json` (`roomscope.i18n.diag`)
  and are translated when shown (`localize`), so files read the same in every
  language, the schemas are unchanged and sessions from earlier versions
  open with their original text. Settings lists languages as 跟随系统 /
  English / 简体中文; a change applies from the next start, so no window is
  left half in one language. On macOS a Finder launch follows the system's
  preferred languages. Terms are unified (扫频, 回送, 本底噪声, 衰减范围不足,
  独立模式, 通用 DAW 模式). New gates: every extracted message, diagnostic
  template and argparse text has a translation with the same placeholders;
  the GUI pages, dialogs, reports, charts and CLI help in zh_CN show no
  English beyond an explicit list of product, standard and DAW names; the
  installer has both languages; README and each Chinese document link their
  counterpart.
- **Audio device inventory** (`roomscope.audio.inventory`, `roomscope devices
  --probe | --host-apis | --json`): every host API and device PortAudio sees,
  the sample rates each accepts for one channel (`Pa_IsFormatSupported`;
  nothing is played), PortAudio's default latencies, the entries that are one
  physical device across host APIs (MME's 31-character names included), and
  the recommended entry per device and direction (a direct path first — ALSA
  `hw:`, WDM-KS, ASIO, JACK — then the platform's host-API order). Each
  host API carries its measurement-relevant behaviour, from
  `docs/AUDIO_DEVICES.md` (+ zh-CN; 38 references: PortAudio v19.7 source,
  python-sounddevice, Microsoft, Apple, ALSA / PipeWire / JACK documentation,
  Farina 2007, Müller & Massarani 2001, Torras-Rosell & Jacobsen 2011, Novák
  et al. 2015 and others).
- **Basic support for every device path in Standalone Mode**: one host API
  per take (PortAudio refuses mixed host APIs, `paBadIODeviceCombination`;
  an unset side takes the same host API's default device instead of MME's),
  channels checked against the device before anything is played, a warning
  when playback and recording are separate devices on separate clocks, and
  `roomscope measure --latency low|high`, `--wasapi-exclusive` (no Windows
  audio engine) and `--coreaudio-set-rate` (set the macOS device rate and
  refuse to convert). WASAPI's auto-convert is deliberately not offered: it
  inserts the engine's resampler.
- `roomscope doctor` (`--probe`, `--json`) and **Help ▸ Environment Report
  for Bug Reports** in every edition: the version and the build commit of a
  desktop bundle (`build_info.json`, written by the PyInstaller spec; release
  smoke tests require it to match the built commit), the versions of NumPy,
  SciPy, libsndfile, PortAudio and Qt (from the module when a bundle carries
  no package metadata), the settings that change a measurement (the output
  folder only as set / not set), paths with the home folder as `~`, host
  APIs and every device, and on request the sample rates each accepts
  (nothing is played). The dialog copies the text, opens the data folder and
  the issue-template chooser; nothing is sent automatically.
- Issue templates for **audio interface test reports** and **DAW
  compatibility reports**, the only source of the cells in
  `docs/HARDWARE_TESTS.md`. The interface report asks Pass / Fail / Not run
  for each row of the hardware matrix (44.1, 48 and 96 kHz as separate takes,
  channels above 2, loopback, Stop, dropouts, unplugging) and says where the
  log is; the DAW report asks for the interface, the "Impulse response:" line
  with its direct-sound confidence and the environment report. The bug
  template asks for the install type, expected and actual behaviour and the
  environment report. Template links are absolute (relative links in issue
  forms resolve against the issue URL). The README has a short "Help test"
  section linking both forms.
- Developer tools with two defaults (`roomscope.edition`,
  `ROOMSCOPE_EDITION`): a source or pip install shows them (the developer
  defaults), a bundle of either edition hides them (the installed defaults).
  The developer defaults add a Developer
  menu (Audio Device Inspector with rate probing and JSON copy, Open Data
  Folder) and advanced audio options in Standalone Mode
  (latency, WASAPI exclusive, Core Audio set-rate). Settings gain *Theme*
  (system / light / dark, applied at once) and *Show developer tools*, and a
  save keeps the fields the dialog does not show.
- Standalone Mode lists devices per host API (the platform's preferred one
  preselected), stars the recommended input and output, and checks host API,
  channels and separate clocks before playing.

### Changed
- **Reports lead with "At a glance"**: reverberation, early reflections, low
  end, noise floor and data quality in one line each, with the symbol the
  recording profile's findings give that topic. The detail follows in the
  order reverberation, noise, reflections, placement, resonances,
  diagnostics, interpretation. Nothing was removed.
- **Comparison report**: its own "At a glance"; the decay deltas grouped by
  band in a table that fits 60 columns (each "not compared" reason listed
  once); background noise per band in dB; resonance and loopback sections.
- **Errors**: one block for every user error (`× error: …`, an explanation,
  the commands to try), including argparse's usage errors, files and
  folders that cannot be read or written, and unexpected failures; a
  traceback only with `--verbose`. Exit codes unchanged.
- **Help**: commands in workflow order, a short usage line per command,
  required options listed first, options grouped, metavars that say what to
  give (`WAV`, `DIR`, `HZ`, `DBFS`), a default only where it tells you
  something, and examples on every core command.
- The terminal layout honours `FORCE_COLOR`; a stream that cannot encode
  `✓`, `→` or `Δ` gets ASCII forms; text is laid out for at most 100 columns;
  numbers are never separated from their units by a line break.
- The GUI's "Full report" panes show the same reports as the terminal:
  `cli/render.py` is the one report layout, and `cli/report.py`'s
  `format_report` / `format_comparison_report` now return that layout as
  plain text.
- `roomscope doctor` names the edition (Desktop or Terminal) and whether the
  developer tools are shown.
- **macOS signing prepared for a Developer ID** (none exists yet; releases
  stay ad hoc signed, not notarized). `packaging/macos/sign_app.sh` signs
  inside out (loose Mach-O files, nested frameworks deepest first, then the
  app) instead of `codesign --deep`, which Apple advises against for
  signing; `--identity` adds the hardened runtime, secure timestamps and
  `entitlements.plist` for a future Developer ID build. The release job
  rehearses that layout on arm64 and x86_64 with an ad hoc hardened-runtime
  copy (`entitlements-adhoc.plist`) that must start and create PortAudio's
  cffi callbacks; `roomscope doctor` reports whether callbacks work (a
  hardened runtime without `allow-unsigned-executable-memory`, or SELinux,
  would stop every recording). Steps and sources: `docs/RELEASE_PLAN.md` §3b.
- **GUI redesign.** One design system (`ui/theme.py` tokens, a generated Qt
  style sheet, Fusion on every OS so Windows, macOS and Linux render alike,
  light and dark schemes) and shared widgets (`ui/widgets.py`). Home: mode
  cards and the product's three principles; the session list shows room,
  position and local time. DAW and Standalone pages: page header, scrolling
  step cards, primary actions, safety and demo banners. Results: key figures
  (RT60, background noise, early reflections, direct-sound confidence) each
  with a validity or trust chip, findings as coloured cards with translated
  severity and topic, the band table in full; the text report moved to a
  *Full report* tab. Plots share the series palette; minor grid lines follow
  the scheme; spin and combo boxes use drawn chevrons. The window has a drawn
  app icon. All new strings are in the zh-CN catalog.
- Compare page: page header, a session-picker card and the results in tabs
  (metrics, frequency-response difference, early reflections, resonances,
  full report); the difference chart follows the scheme.
- **Readable, translated results and comparisons.** Chart titles, axis
  labels and legends are translated; charts in Chinese use an installed CJK
  font (PingFang SC, Microsoft YaHei, Noto Sans CJK SC and others) after
  DejaVu Sans, where they drew empty boxes before. The compare table names
  metrics ("63 Hz T20 (s)", "Background noise, RMS (dBFS)") instead of ids
  and translates validity and match status; the metric id and the reason
  for a missing delta are tooltips. Profiles are listed by name ("Room
  microphone"); files and `--profile` keep the id. Plots are laid out again
  when resized, so axis labels are no longer clipped. The text report
  translates the direct-sound confidence and the broadband row.
- **matplotlib>=3.10** (was >=3.8). The wheels of 3.8.0, 3.9.0 and 3.9.4
  still contain the `_ttconv` extension that DEPENDENCIES.md §6 said was gone
  from 3.8; 3.10.0 is the first without it (wheels opened 2026-09-24). With
  the other declared minimums (numpy 1.26, scipy 1.12, soundfile 0.12,
  sounddevice 0.4.6, PySide6_Essentials 6.6) the suite passes 522/522 on
  Python 3.12; with the newest releases it passes on 3.13 and 3.14.
- The `dev` extra adds PyYAML (MIT; tests only) so the check that keeps each
  English GitHub issue form and its Chinese counterpart in step runs in CI.
- The `dev` extra lists `hatchling` (MIT; already the build backend) so the
  wheel build-hook test runs in CI (DEPENDENCIES.md §2).
- `SECURITY.md` names the supported versions and how files received from
  other people are treated; `docs/HARDWARE_TESTS.md` gains two rows
  (no logged buffer problem in a full take; an unplugged device is reported
  as a failure) and says what the automated backend tests do not show.
- Coverage of `core` + `models` (branch coverage, the CI gate's measure) is
  90.20 % (87.74 % on 0.4.0); the run is recorded in `docs/STATUS.md`.

### Fixed
- `roomscope export` no longer logs *ignoring third-party exporter 'csv';
  name collides* on every run: `pyproject.toml` registers the built-in CSV
  exporter under the `roomscope.exporters` entry-point group as well (the
  documented extension point), and the registry took its own declaration
  for a third-party one. A different exporter that reuses the name is still
  reported and ignored.
- The desktop and terminal bundles honour `PYTHONIOENCODING`, which their
  frozen interpreter ignores: `roomscope --lang zh_CN demo` piped with
  `PYTHONIOENCODING=utf-8` on Windows failed with `UnicodeEncodeError`
  instead of writing UTF-8.
- **`roomscope gui` without PySide6 printed a traceback.** The friendly
  message in `cmd_gui` guarded only the import of `roomscope.ui.app`, which
  does not import Qt, so a wheel installed without `[gui]` (or a Linux system
  without the Qt libraries) crashed with `ModuleNotFoundError`. `roomscope gui`
  and the `roomscope-gui` entry point now check PySide6 first and explain how
  to add it (`pip install "PySide6_Essentials>=6.6"`, not `roomscope[gui]`,
  which PyPI does not have), in English and Simplified Chinese. Found by
  installing the release candidate's wheel in a clean environment.
- `roomscope --format json measure` printed the safety note and the status
  lines on stdout before the JSON document, so the output could not be
  parsed; they now go to stderr. `doctor` and `devices` ignored the global
  `--format json` and printed text; they now print JSON.
- **A complete take could be discarded by its progress display.** The last
  block reaches 100 % before PortAudio calls the finished callback (it
  drains the output first); a progress poll in that gap called the front
  end inside the stream loop, and a failing callback (a window already
  closed) escaped as "playback/recording failed" (seen once on CI #58,
  macOS). Progress failures are now logged once and never stop or discard a
  take; a scripted stand-in with a finish delay reproduces it
  deterministically.
- **Standalone device choice (review findings).** The page preselected the
  lowest-numbered starred device instead of the system's: on a Mac, where
  every Core Audio device is its own starred entry, a virtual device such as
  BlackHole could be played into and recorded from. "System default" now
  stays selected, a chosen host API preselects its own default devices, and
  a star is only a hint. `--wasapi-exclusive` (and the GUI option) was
  refused by a shared-mode rate check before the exclusive stream was
  opened: the pre-flight now asks with the stream's host-API settings. The
  fake backend's host API has default devices again, so choosing one side
  works.
- **Desktop bundles.** Every launch of a frozen app rebuilt matplotlib's font
  cache (PyInstaller's runtime hook sets a new temporary `MPLCONFIGDIR` per
  start; Release #14 logs show 14-17 s before the window appeared); the cache
  now lives in `$ROOMSCOPE_HOME/cache/matplotlib-<version>`. The Linux
  tarball no longer carries the build runner's `libportaudio`, `libasound`,
  `libjack` and Berkeley DB: it uses the system's PortAudio, as the user
  guide says, so the distribution's ALSA plugins (PipeWire's among them) are
  found. The macOS app declares `LSMinimumSystemVersion` 14.0, the minimum
  of the bundled NumPy / SciPy wheels (`macosx_14_0`); the docs said
  macOS 13+. The release notes and user guides give the Gatekeeper path that
  works on macOS 15+ (Privacy & Security → Open Anyway; right-click → Open
  no longer bypasses it). The uninstall check requires the whole install
  folder to be gone, and the bundle smoke requires every library version in
  `doctor` and no longer mistakes a pip install's `roomscope-gui` script for
  the bundle's windowed launcher.
- **A bug-report bundle could carry a file from outside the session.**
  `roomscope session bundle` followed symbolic links, so a session folder
  from someone else with a link to, say, a private key put that file into
  the zip meant for a public issue. Files that resolve outside the session
  folder are now left out (with a log line).
- **Buffer under/overflows reached only the log.** A Standalone take whose
  device reported an input overflow (samples dropped) or output underflow (a
  gap in the sweep) was analysed with no sign of it in the GUI. The flags
  now travel with the take (`AudioSignal.device_warnings`) into the result's
  warnings and a translated "measure again" finding
  (`measurement.dropouts`), in the GUI and `roomscope measure` alike.
- **Standalone pre-flight checked the wrong device.** The GUI and
  `roomscope measure` asked for the sample rate before resolving which host
  API the take would use: with one side left at "system default", the GUI
  checked the system default device (MME on Windows) while the stream
  opened the chosen host API's default device, and the CLI skipped that side;
  both asked for the device's maximum channel count instead of the channels
  the stream opens. One `inventory.preflight`, used by both, now resolves the
  devices, checks the channels, then the rate on those devices with those
  channel counts.
- Cross-platform audit (Windows / macOS behaviour emulated in
  `tests/unit/test_cross_platform.py`): CLI output redirected to a file or
  pipe is written as UTF-8 (the locale code page raised UnicodeEncodeError on
  Δ, → or a Chinese room name); `project.json` stores session paths with `/`
  and reads `\` from projects written on Windows, and a session added twice
  is recognised by its resolved path; `roomscope session bundle` refuses a
  destination inside the session folder (the zip contained itself and grew
  without end); copying a file onto itself is detected with `samefile`
  (case-insensitive file systems); the log file keeps working when another
  process holds it during rotation (Windows); default input / output devices
  are marked again (sounddevice returns an indexable pair, not a tuple); the
  display language is read from Windows (`GetUserDefaultUILanguage`) and
  `zh-Hans-CN` / "Chinese (Simplified)" tags map to zh_CN; the session list no
  longer fails on dates Windows cannot convert; a silent recording names the
  macOS microphone permission.
- **Bundle gate (#17).** `scripts/check_bundle_contents.py` matches GPL-only
  Qt QML modules by directory (`qml/QtQuick/VirtualKeyboard`,
  `qml/QtQuick/Timeline`, `qml/QtCharts`, `qml/QtGraphs`,
  `qml/QtDataVisualization`, `qml/QtQuick3D`, `qml/Qt/labs/lottieqt`, also
  inside a macOS `.app`), whose plugin files do not carry the module name
  (`libqtvkbpinyinplugin.so`); `--strip` removes them and the directories it
  empties. A frozen tree that contains any file under a `qml/` directory now
  fails the gate, because RoomScope has no QML UI. A Linux PyInstaller
  6.22.3 build from `requirements/bundle.lock` was built locally: it has no
  `qml/` directory and passes `--strip`.
- **Simplified Chinese (#14).** The catalog now covers all seven profiles
  (28 more findings), and the words inserted into sentences (decay length,
  direction of an RT60 change, noise segment) are translated through
  `pgettext` while findings keep the English word in `params`. The
  Standalone safety warning and the `--acknowledge-level` refusal were
  already translated on `main`; they are now marked for extraction. A
  catalog `.mo` is never written at run time any more (0.4.0 wrote one into
  the installed package); the wheel ships a `.mo` compiled by the build hook
  in a temporary directory, used only while its recorded SHA-256 matches the
  `.po`. Tests run with a pinned English locale. New test: every message
  extracted from `src/` has a translation with the same placeholders, and
  `--lang zh_CN analyze --profile drums|room_mic|acoustic_guitar|choir`
  prints no English finding text.
- **Loopback time origin (#12).** The interface FIR's time origin is now its
  peak (samples before it at negative time) and the division is linear
  (padded frame), so compensation no longer advances the response by the
  5 ms pre-roll; the sweep start and reflection delays stay within one
  sample of the uncompensated analysis. The electrical-settling check
  subtracts the noise floor (estimated at the end of the valid record) from
  the energy before it finds the 99 % point, so a clean loopback with a long
  post-roll is no longer refused, while a close microphone in a live room is
  still refused. `compensate()` now requires `fir_peak_index` (keyword-only):
  the old implicit origin at the FIR's first sample reproduced the shift.
  Kirkeby et al. 1998 is in the methodology references.
- **PortAudio callback (#13).** Progress is reported from the waiting thread,
  never from the real-time callback; an exception in the callback aborts
  the stream and fails the take instead of returning zeros; a stream that
  ends early is an error; Stop no longer waits for the timeout when the
  device has stalled; buffer under/overflow flags are logged. Hardware
  inputs (1-based) and recording columns (0-based) are mapped by
  `plan_input_channels` and validated before anything is played; a loopback
  on the microphone input is refused up front. Sessions store the 1-based
  interface channels of a Standalone take and leave them empty in Universal
  DAW Mode (the CLI stored the 0-based column before).
- **Comparison (#9).** Frequency responses are smoothed on their own grid
  before they are sampled on the comparison grid; the per-octave MAD of two
  takes that differ only in the diffuse tail drops from about 3 dB to below
  1 dB in the 4–16 kHz octaves. A decay band present on one side only is
  reported whichever side lacks it.
- **Imported impulse responses (#10).** The sweep-pass search is skipped
  when there is no sweep: on a loud file it ran in quadratic time (a 6 s
  sweep WAV did not finish in five minutes) and on real IRs it could hide
  the decay and the reflections. A file that is not an impulse response
  (pre-peak margin below 10 dB; the stretch just before the peak is
  excluded for max(2 ms, 2 / declared upper band edge), so a declared
  sub-woofer IR passes) is refused, as is an IR whose direct sound is
  weaker than a later arrival. `analyze-ir` now has tests.
- **Session loader (#11).** `result.json` / `impulse_response.wav` are read
  only from inside the session folder; absolute or escaping paths (and
  symlinks leading out) are refused. Incomplete comparison and calibration
  records raise `SessionError` instead of `TypeError`.
- **ISO 3382-2 classes (#15).** Table 1 is now the standard's (4.3.1:
  combinations 2 / 6 / 12, source positions ≥ 1 / ≥ 2 / ≥ 2, microphone
  positions ≥ 2 / ≥ 2 / ≥ 3, read from the standard's preview pages); 0.4.0
  asked for 3 / 6 microphone positions and did not check them for
  engineering. Every row is checked, including the number of
  source–microphone combinations. `roomscope project average` counts
  distinct position labels, not sessions, so repeated takes at one position
  are no longer labelled a survey-class spatial average; `--sources 0` is
  refused.
- **Source safety check (#16).** `scripts/check_src_safety.py` resolves
  import aliases (`np.load`), reports `from os import system`, star imports
  from `os` / `numpy`, the `os.exec*` / `os.spawn*` / `os.fork` families and
  `asyncio.create_subprocess_*`, and treats `importlib.import_module` /
  `__import__` like an import. It is a lint, not a sandbox.
- Methodology reference numbers [17] / [18] were used twice; Allen & Berkley
  and Dokmanić et al. are now [20] / [21].
- `mypy --strict` is also clean when the PySide6 6.11 typed stubs are
  installed.
- **A Standalone or demo take is never blamed on a DAW.** The playback-speed
  check (added in this version) ran on every take whose direct sound was not
  identified, including takes RoomScope played itself; on a noisy or very
  reverberant take its estimate is biased, and the report then advised
  switching off a DAW's time-stretching that was never there. The check now
  runs only on imported recordings.
- **`--wasapi-exclusive` / `--coreaudio-set-rate` on another host API are
  refused.** `roomscope measure --wasapi-exclusive` without a WASAPI device
  (for example on the MME default) ran a shared-mode take without a word; the
  pre-flight now stops with a message naming the device's host API. The GUI
  already offered each option only for its host API.

### DAW workflow
- **Wrong sweep speed is diagnosed.** A DAW that plays the test signal at the
  wrong speed (a 48 kHz file in a 44.1 kHz project without conversion, or
  Warp / Flex Time / Follow Tempo / elastic audio) made the analysis report only "direct-sound detection confidence is
  low" or "recording is shorter than the reference sweep".
  `roomscope.core.playback_speed` measures the sweep rate in the recording
  (for every frequency bin the frame where the passing sweep peaks; a
  Theil-Sen line through time against ln f) and names the cause: a
  sample-rate mismatch when the played rate is within 2.5 % of a common rate,
  otherwise a time-stretch. It runs only when direct-sound detection
  confidence is low (a medium margin means the sweep did deconvolve), marks the decay unreliable, is stored as
  `impulse_response.playback_speed` in `result.json` (optional, additive
  schema field), and is added to the "shorter than the reference" and
  "starts after the sweep began" errors. New findings
  `measurement.playback_sample_rate` / `measurement.playback_time_stretch`
  replace the generic direct-sound finding; both are translated. Synthetic
  tests: a sweep played unconverted at 44.1 / 88.2 / 96 kHz, a 44.1 kHz
  project exported at 48 kHz, ±3 % stretches, a sweep-less noise file.
- **DAW export formats.** New tests analyse the same take as Broadcast WAV
  with `bext` / `iXML` / `JUNK` chunks (Pro Tools), WAVE_FORMAT_EXTENSIBLE,
  RF64, Wave64, AIFF, CAF (Logic Pro recordings) and FLAC, at 16 / 24 /
  32-bit PCM and 32-bit float, and stereo bounces of a mono microphone. The
  GUI's recording dialog lists all of those extensions (it offered only
  `.wav .flac .aif .aiff`, so Logic's CAF files and `.w64` exports were
  hidden) plus *All files*.
- **Per-DAW guide.** `docs/user-guide/daw-setup.md` (and zh-CN): the rules
  every DAW must follow (sweep at the project rate, no time-stretching, no
  plug-in or room correction on the playback path, one loudspeaker, input
  monitoring off, one pass, whole export without normalising), step-by-step
  notes for Pro Tools, Logic Pro / GarageBand, Cubase / Nuendo, Studio One,
  Ableton Live, REAPER, FL Studio, Bitwig Studio and Audacity, and a table
  from each report message to its DAW cause. The notes come from the DAWs'
  documentation; `docs/HARDWARE_TESTS.md` gains an empty per-DAW matrix for
  checking them. The GUI's Step 2 text names those rules.

### Packaging
- **Developer ID signing and notarization, ready but off.** The bundle job
  has the steps for a Developer ID Application certificate: a temporary
  keychain (`packaging/macos/import_certificate.sh`), inside-out signing
  with the hardened runtime and a secure timestamp, then a signed DMG
  submitted to `notarytool`, stapled and checked with `spctl`
  (`packaging/macos/notarize_dmg.sh`). They run only when all six
  repository secrets exist and never on pull requests; with none set the
  build stays ad hoc as before, and a partial set fails the build.
  Nothing has been signed with a Developer ID or notarized yet. The bundle
  job is now named `Bundle (<os>)`. `docs/RELEASE_PLAN.md` §3b lists the
  secrets and why there are two DMGs rather than one Universal app.
- **macOS app opens the GUI.** `RoomScope.app` has its own windowed
  executable, so a Finder launch without arguments opens the GUI; the DMG is
  mounted, copied and launched in the release workflow
  (`scripts/check_macos_dmg.py`).
- **Windows and Linux desktop launch.** The bundles gain a windowed
  `roomscope-gui` launcher next to the console `roomscope`, sharing its
  libraries. Started without arguments (Explorer, the Start menu, a desktop
  file, the AppImage `AppRun`) it opens the GUI; before, those launches ran
  the console CLI, which printed its usage and exited, so a double-click
  never showed a window. With arguments both executables are the CLI.
- **Windows installer.** The release workflow installs Inno Setup when the
  runner lacks it and always builds `RoomScope-Desktop-Windows-x64-Setup.exe` (per-user, no
  administrator rights; Start-menu and optional desktop shortcuts to
  `roomscope-gui.exe`; upgrades replace the previous libraries). The
  installer is written to `dist/` (it went to `packaging/windows/Output`),
  its version comes from `pyproject.toml` via `/DMyAppVersion`, and the
  workflow installs it silently, smoke-tests the installed copy and
  uninstalls it.
- **Build without GitHub Actions.** `scripts/build_release.py` runs the
  release workflow's bundle job on the local machine (tests, license bundle,
  PyInstaller, `--strip` gate, smoke test, archive / installer / DMG,
  `SHA256SUMS-<OS>-<ARCH>`, optionally wheel and sdist) with the workflow's
  file names, and refuses packages that differ from `requirements/bundle.lock`;
  `docs/RELEASE_PLAN.md` §3a describes publishing such a build by hand.
- `scripts/smoke_bundle.py` also runs `gui --smoke` through the windowed
  launcher; `--require-gui-launcher` fails a Windows / Linux bundle without
  one.
- The Release carries one `SHA256SUMS` for every download instead of one
  file per build machine; the draft refresh removes the earlier names.
- **Intel Macs.** The release workflow also builds on an Intel macOS runner;
  the disk images are `RoomScope-Desktop-macOS-arm64.dmg` and
  `RoomScope-Desktop-macOS-x86_64.dmg` (was `RoomScope.dmg`, Apple silicon only),
  each checked for its own architecture, and the checksum files are named per
  runner OS and architecture (`SHA256SUMS-macOS-ARM64`, ...).
- **The draft Release holds exactly one run's files.** The draft job no
  longer uses `softprops/action-gh-release`, which looks a release up by tag
  and cannot see a draft: each run opened a second draft, fell back to the
  older one, uploaded over same-named files and left renamed ones
  (`RoomScope.dmg`, `SHA256SUMS-macOS`, ...) and the first run's notes in
  place. `scripts/release_draft.py` now checks that the run produced exactly
  the expected files and that every runner's `SHA256SUMS-*` matches its archives
  (also on pull requests), then finds the single draft by tag or title,
  refuses a published release, several drafts, a tag on another commit or an
  asset it does not know, replaces all assets, notes, tag and target, and
  reads the draft back (names, sizes, GitHub's SHA-256 digests, target,
  draft, pre-release). Assets are deleted only from a release re-read as a
  draft just before. The draft job also checks the commit is on `main` and
  never runs twice at once.
- The license bundle carries libsndfile's LGPL-2.1 text and the source notes
  for the libraries inside it, which soundfile keeps outside its metadata
  (`THIRD_PARTY_LICENSES/soundfile/`, `_notices/libsndfile.txt`).

### Documentation
- **Download first.** README and README.zh-CN open with the download: the
  stable [Releases page](https://github.com/jingyemingyue/RoomScope/releases)
  (not `/releases/latest`, which never shows a pre-release), a Desktop
  Edition table, a Terminal Edition table and a comparison of the two, the
  first-launch steps for unsigned builds through the normal macOS / Windows
  dialogs (no Gatekeeper or SIP changes), then a 30-second demo; the
  developer install and the architecture moved below the user sections. New
  `docs/INSTALLATION.md` (+ zh-CN): macOS, Windows (installer and ZIP),
  Linux, the Terminal Edition and the Python installs, checksums, updating,
  uninstalling, unsigned-build warnings (Smart App Control included),
  supported systems (glibc 2.39 for the Linux bundles) and troubleshooting;
  the user guide's install section names every Release file, the Linux
  system libraries and the wheel install (RoomScope is not on PyPI yet).
  The Linux notes name a CJK font for Chinese chart text.
- **Release notes for testers.** `packaging/release-notes-header.md` opens
  with *RoomScope v<version> — Early public pre-release for testing*, then
  *Choose your edition* (the Desktop table, then the Terminal table) with
  the first-launch steps, *Known limitations*, *Checksums*, the changelog
  (the draft job inserts this section there) and the technical information
  (what works, wheel, SBOM, lock). `tests/unit/test_release_notes.py` fails when a
  download file named there or in the user documents is not one the Release
  carries, when an earlier file name remains, or when a README does not show
  both editions before anything else.
- `scripts/render_readme_assets.py` regenerates the README images from the
  demo (`docs/images/cli-demo*.svg`, GUI screenshots stamped "synthetic demo
  data", the social preview); see `docs/SCREENSHOT_PLAN.md`.
- RELEASE_PLAN §3c (publishing v0.4.1 as the first public pre-release: what
  was checked on the release candidate and the publish checklist) and §3d
  (PyPI readiness: name free, metadata passes `twine check`, trusted
  publishing wired but off, README links not yet PyPI-ready).
- `docs/HARDWARE_TESTS.md` ends with a step-by-step for testers: safety,
  install per system, what to do and what counts as a pass for each row of
  the interface form, buffer and latency settings, one DAW take, and what
  to attach.
- `docs/COMPATIBILITY.md` (+ zh-CN): platforms, Python and dependency floors,
  DAW export formats, host APIs and cross-platform behaviour, each with what
  verified it (CI job, local build, test module) and what is not verified.
- `docs/EDITIONS.md` (+ zh-CN): the Desktop and Terminal Editions, what each
  contains, and the developer tools (developer and installed defaults, how
  to switch).
- `docs/user-guide/daw-setup.md` (+ zh-CN) rewritten from each vendor's
  current documentation, with a numbered source per step (a documented
  workflow; no step has been run in a DAW with RoomScope yet): Pro Tools
  (Apply SRC is
  not a mismatch indicator; TrackInput off still monitors while recording),
  Logic Pro 12.3 (*Flex* + *Smart Tempo* replace *Flex & Follow*), GarageBand
  (no sample-rate setting; *Export projects at full volume* normalises),
  Cubase / Nuendo (*Convert to Project Settings*, Auto Monitoring *Manual*,
  Export Selected Events *Dry*), Fender Studio Pro 8 (formerly Studio One;
  the track's *Tempo* mode), Live (*Auto-Warp Long Samples* is on by
  default), REAPER (*Request sample rate*; the default *Beats* timebase),
  FL Studio (monitor and loop-record defaults), Bitwig (*Stretch* mode
  *Raw*; there is no *Off*), Audacity 3.4+ (*Record New Track*, *Export
  Audio* with *Current Selection*), MOTU Digital Performer 12, and a
  checklist for any other DAW with Ardour and Cakewalk notes. Rules added:
  no plug-ins on the microphone track; exporting at another rate is
  harmless; a small stretch is not named by the diagnosis.
- **Speed diagnosis on short sweeps.** A correctly played short sweep in a
  reverberant synthetic room measured up to 4.5 % off (1 s sweep) and was
  named a time-stretch. The "as generated" band now follows the estimate's
  measured spread, `max(1.25 %, 5.5 % / T^0.75)` for a `T`-second sweep
  (1.25 % at 10 s, 2.4 % at 3 s, 5.5 % at 1 s); a 44.1 / 48 kHz mismatch is
  still named from about 0.6 s.
- A recording whose quiet part is exact digital silence gets a warning
  finding (`measurement.digital_silence`): the DAW's test-signal track
  exported instead of the microphone otherwise analysed as a near-perfect
  room with an RT60 of a few hundredths of a second.
- `docs/COMPARISON.md` (+ zh-CN): a sourced comparison with REW, Open Sound
  Meter, ARTA, Smaart, SoundID Reference, ARC X, Dirac Live, HouseCurve,
  AURORA, pyroomacoustics, python-acoustics, pyrato and ITA-Toolbox, what
  RoomScope does differently, and when another tool is the better choice;
  README gains "What makes RoomScope different".

## [0.4.0] - 2026-09-24

First pre-release. Everything below was developed against synthetic rooms;
no hardware result is claimed, the desktop bundles are unsigned, and the
repository is still private. Review follow-ups are tracked as issues
#9–#16 (see `docs/RELEASE_PLAN.md` §6).

### Added
- Release plan (`docs/RELEASE_PLAN.md`, zh-CN digest): version ladder
  0.4.0 → 0.4.x → 0.5.0 → 1.0.0rc1 → 1.0.0 with the gates for each, and
  the version-driven release pipeline: a version change in `pyproject.toml`
  on `main` builds sdist/wheel, unsigned bundles for Linux, macOS and
  Windows, a CycloneDX SBOM and checksums, and opens a **draft** GitHub
  Release; publishing the draft is the maintainer's decision and is what
  creates the tag. PyPI upload runs only on a tag and only when the
  repository variable `ROOMSCOPE_PUBLISH_PYPI` is `true`. The workflow
  file itself is installed by the maintainer (RELEASE_PLAN.md §3).
- Verbatim LGPL-3.0, GPL-3.0 and PortAudio license texts under
  `packaging/licenses/`; `scripts/build_license_bundle.py` ships them in
  `THIRD_PARTY_LICENSES/_texts/` and fails when PySide6 is installed but
  the LGPL / GPL texts are missing (DEPENDENCIES.md §3–§4). The About
  notice points at those files.
- `scripts/check_bundle_contents.py --strip` deletes GPL-only Qt modules
  and ASIO DLLs from a frozen tree before the gate runs. The gate now
  recognises versioned Linux libraries (`libQt6QuickTimeline.so.6`),
  macOS framework binaries and the `Qt6`-prefixed file names
  (`Qt6VirtualKeyboard.dll`), which the previous name check missed;
  `--require-licenses` also requires the verbatim texts.
- 1.0-rc software that does not need hardware or a public flip: GUI
  Placement tab and tape-measure fields (S5); Python 3.14 in the CI
  matrix (S6); the M11 validation protocol with pre-chosen tolerances
  (`docs/VALIDATION.md`); `requirements/bundle.lock`; `CODEOWNERS`; docs
  link check; 85 % coverage gate on `core` and `models`; `docs/index.md`
  hub; fixtures README; keyboard shortcuts for every main action; plots
  use linestyle as well as colour; GitHub Actions pinned by SHA; themed
  documentation site (`scripts/build_docs_site.py`, S7); matplotlib / Qt
  chrome follows the system dark mode; Standalone shows the device rate
  next to the requested rate and calls `check_sample_rate` before a
  measurement; Compare lists matched reflections, resonances, loopback
  deltas and per-octave MAD; Help opens the license bundle or
  `docs/DEPENDENCIES.md`. JSON reads cap nesting depth as well as size;
  settings, recents and sweep sidecars use the same reader.
  `scripts/check_src_safety.py` bans network imports, pickle, eval and
  shell-outs under `src/`. Unsigned-bundle packaging adds Inno Setup, a
  Linux desktop/AppRun, a macOS dmg script, zip/tar archives and
  `scripts/smoke_bundle.py` (fake-backend measure, offscreen GUI).
  Linux x86_64 and Windows win_amd64 wheels of numpy/scipy/soundfile/
  sounddevice/matplotlib/Pillow were opened
  (`scripts/audit_wheel_contents.py`); the Windows sounddevice wheel
  ships ASIO DLLs that the bundle gate strips. `load_comparison` and
  `roomscope show comparison.json` re-derive findings (they are never
  stored); robustness tests cover comparison.json, more WAV/sidecar cases
  and a microphone used as loopback. CLI `--help`, text-report labels,
  DAW / Standalone / Results chrome and the remaining CLI messages go
  through gettext.
- v0.4 for everyone (ARCHITECTURE_V1.md milestone 0.4): gettext with a
  Simplified Chinese catalog for the `generic`, `vocal` and `voiceover`
  profile findings, the report labels, GUI chrome and CLI help (the other
  four profiles and the Standalone safety warning still fall back to
  English — #14); `--lang` / `settings.language` / `ROOMSCOPE_LANG`; user
  settings under `$ROOMSCOPE_HOME/settings.json`; self-contained sessions
  (sweep sidecar always copied, recording copied on `--copy-recording` /
  the GUI default); `roomscope session bundle` (`--no-audio`); project
  folders and `average_decay` (SHOULD; the ISO 3382-2 class thresholds are
  a secondary-source transcription, see #15); CSV exporter and
  `roomscope export`; user guide in English and Chinese; macOS
  `NSMicrophoneUsageDescription` and audio-input entitlement. `--json` is
  deprecated in favour of `--format json` (stderr warning only).
- v0.3 trust-the-chain (ARCHITECTURE_V1.md milestone 0.3): optional
  loopback compensation (`core/loopback.py`, `--loopback` /
  `--loopback-channel`); `AudioBackend` protocol with a fake backend and a
  PortAudio callback stream that honours progress and Stop; CLI
  `--backend`; GUI Demo mode, Stop, and a loopback channel; robustness
  tests and a JSON size cap; CI on Linux, macOS and Windows; hardware
  matrix started in `docs/HARDWARE_TESTS.md` (no cell is marked PASS).
- v0.2 reopen-and-compare (ARCHITECTURE_V1.md milestone 0.2): lazy Tier 1
  exports on `import roomscope`; lenient `from_dict` loaders; shipped JSON
  Schemas and `roomscope schema`; `compare()` of two `AnalysisResult`s with
  a validity on every delta; CLI `roomscope compare` and `analyze-ir`;
  `interpret_comparison`; GUI pick-two compare view with an explicit
  "input gain unchanged" checkbox. `jsonschema` is a dev dependency used
  only in tests.
- Session re-opening: `AnalysisResult.from_dict` rebuilds a saved result;
  `load_measurement` reloads `session.json` + `result.json` + the IR WAV;
  `list_sessions` finds session directories. CLI `roomscope show` prints a
  saved report (`--list` browses a folder). The GUI Home page has Open
  Session, Browse Folder and a recent-session list; File → Open Session
  does the same. Saves and opens are remembered under `$ROOMSCOPE_HOME`
  (`~/.roomscope` by default). `MeasurementSession.recording_profile`
  records which interpretation was used.
- v1.0 architecture design (`docs/ARCHITECTURE_V1.md`, Chinese digest in
  `docs/ARCHITECTURE_V1.zh-CN.md`): public API tiers, schema policy,
  session comparison, loopback reference channel, audio backend interface,
  internationalisation, packaging and release pipeline, quality and
  validation gates, milestones with exit criteria, and the decisions
  reserved for the maintainer.
- GitHub project files so other developers can clone, review and open pull
  requests: CI (pytest on Python 3.12/3.13, ruff, mypy, sdist/wheel), issue
  and pull-request templates, Dependabot, Contributor Covenant, and a
  security policy.
- Project foundation: Apache-2.0 license, architecture and methodology
  documents, dependency / third-party / provenance / license-decision audits.
- Python package `roomscope` (src layout, typed, ruff + mypy clean).
- DSP core: exponential sine sweep generation with analytic (Farina) and
  regularised spectral inverse filters; whole-recording deconvolution with
  automatic impulse-response location; Schroeder decay with Lundeby noise
  truncation and late-decay compensation; EDT / T20 / T30 / estimated RT60
  per ISO 3382-1 evaluation ranges with validity flags; time-reversed
  octave-band filtering with B*T check; frequency response with
  fractional-octave smoothing; background noise (dBFS, PSD, 50/60 Hz hum
  detection); early-reflection candidates; potential low-frequency
  resonance candidates.
- Placement geometry (`core/placement.py`): the vertical axis derived from the
  early reflections plus one or two tape measurements, in three tiers that
  degrade explicitly as inputs are withheld. Reports the loudspeaker height,
  the plane above both devices and the horizontal separation; never a
  coordinate, a room length or width, or a named wall, because one
  omnidirectional microphone at one position leaves the system underdetermined
  by two even with a measured loudspeaker distance. New CLI flags
  `--speaker-distance`, `--mic-height`, `--temperature`.
- Measurement session model and JSON/WAV storage.
- CLI: `roomscope sweep | analyze | devices | measure | gui`.
- Interpretation layer with a generic recording profile.
- Recording profiles (`interpretation/profiles.py`): seven profiles —
  generic, vocal, voiceover, acoustic_guitar, drums, room_mic, choir — with
  per-profile reflection/decay/noise thresholds and tailored advice on top of
  shared measurement-integrity checks. CLI `--profile` (`--profile vocal`),
  `Interpretation (<profile> profile):` in the report, and a profile selector
  in both GUI measurement modes.
- Minimal PySide6 GUI (Universal DAW Mode, Standalone Mode, results tabs).
- Synthetic test suite (unit, integration, offscreen GUI smoke tests).

### Changed
- The optional `gui` extra depends on `PySide6_Essentials` only, so a
  developer install does not pull GPL-only Qt Addons modules. `roomscope.ui.qt`
  defines `PySide6.__version__` so matplotlib's QtAgg backend still imports.
- The new release workflow attaches archives and checksums only (not the
  unpacked bundle directories), pins PyInstaller to `>=6.11,<7`, restricts
  `contents: write` to the draft-release job, and names archives by
  version and platform.

### Fixed
- The installed-wheel audit test failed on macOS CI: numpy's
  `macosx_14_0_arm64` wheel (what `macos-latest` installs) links Apple
  Accelerate and bundles no shared library at all, while the
  `macosx_11_0` wheel bundles OpenBLAS with libgfortran / libquadmath under
  `numpy/.dylibs/`. The test accepts either layout and rejects a mixed one;
  DEPENDENCIES.md §6 records both. (An earlier fix attributed the failure
  to `RECORD` omitting the `.dylibs/` folder; that was not the cause.)
- Comparison findings quote ISO 3382-1's "not enough to call the change
  significant" disclaimer. The 0.2 test now requires that wording instead
  of forbidding the word "significant".
- The wheel build includes each shipped `*.schema.json` file without
  adding `roomscope/schemas/__init__.py` twice.
- The results overview now names the recording profile that produced the
  findings. It previously always printed `generic`.
- Loopback deconvolution tests asserted a time-domain IR peak of 1.0 after
  inverse filters were changed to unit *in-band* gain. They now compare
  against `reference_pulse()`. Methodology docs matched the implementation.

[Unreleased]: https://github.com/jingyemingyue/RoomScope/compare/v0.5.0b1...HEAD
[0.5.0b1]: https://github.com/jingyemingyue/RoomScope/compare/v0.4.1...v0.5.0b1
[0.4.1]: https://github.com/jingyemingyue/RoomScope/releases/tag/v0.4.1
[0.4.0]: https://github.com/jingyemingyue/RoomScope/releases/tag/v0.4.0
