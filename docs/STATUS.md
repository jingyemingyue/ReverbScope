# Status

Snapshot: 2026-09-17, v0.1.0.dev1 (foundation). Everything below was
verified by actually running it on macOS (Apple silicon, Python 3.12.14).
Nothing is marked PASS that was not run.

Snapshot 24: 2026-09-27 — **presentation and first run** (CHANGELOG
`[Unreleased]`): `roomscope demo`, "At a glance" summaries, CLI help /
progress / colour, README and README.zh-CN rewritten, hardware-testing
guide and issue form, README screenshots from the synthetic demo. No change
to `roomscope.core`, the schemas or the runtime dependencies. **What was run
for this snapshot** (Linux x86_64, CPython 3.12.3, `dev` + `gui` extras,
PySide6_Essentials offscreen): the full suite, **487 passed**; the CLI,
i18n and catalog tests (53) also on CPython 3.13.12 and 3.14.0rc2; branch
coverage of `core` + `models` 90 %; `ruff check`, `ruff format --check`,
`mypy` (strict, 71 files), `check_src_safety.py`, `check_doc_links.py` and
a link check of the root Markdown files; `uv build` of sdist and wheel and
`twine check` (both PASSED); a fresh CLI-only install of that wheel ran
`roomscope demo` in English and `--lang zh_CN`, and `roomscope gui` printed
the install hint (it raised a traceback before this change). **What was not
run here:** CI on macOS / Windows, the full suite on Python 3.13 / 3.14,
any bundle build, any hardware cell. The hardware matrix and the validation campaign are
still empty.

Snapshot 23: 2026-09-24 — **v0.4.1 workflow verification on PR #18**,
commit `ec9a6b7406e5788830dbe68931899671df0d94d4`.
GitHub Actions CI #43 completed successfully (Ubuntu Python 3.12/3.13/3.14,
macOS Python 3.12, Windows Python 3.12; lint, mypy, schemas, package and
installed-Essentials license gate). Release workflow PR run #1 also completed
successfully: lint/type check, 470 Linux tests and the 85 % coverage gate,
sdist/wheel, SBOM, and **Linux, macOS and Windows frozen bundles** built from
the pinned runtime lock; each passed the `--strip --require-licenses`
bundle gate and a fake-backend/offscreen-GUI smoke test. The macOS `.app`
executable was smoke-tested separately. The workflow uploaded the three
archives, checksums, wheel/sdist and SBOM as **CI artifacts**. Draft Release
and PyPI jobs were skipped on this PR. Windows produced a zip; `iscc` was
not installed, so no Windows setup EXE was produced. No bundle was installed
on a person's desktop and no hardware-matrix cell was executed. The PR
remains unmerged at this snapshot.

Snapshot 22: 2026-09-24 — **v0.4.1, review follow-ups #9–#17** (branch
`v0.4.1-review-followups`, one pull request; see CHANGELOG `[0.4.1]`). Each
issue got a synthetic test that was checked to fail on 0.4.0 and pass
after the fix. **What was run for this snapshot** (Linux x86_64, Ubuntu,
CPython 3.12.3, the `dev`, `gui` and `i18n-dev` extras, PySide6_Essentials
6.11.2, numpy 2.5.3, scipy 1.18.1): the full suite, **470 passed**
(tests/unit 366, tests/integration 54, tests/ui 12 offscreen,
tests/robustness 38), and again on CPython 3.13.13; the CI coverage gate
command (`--cov=roomscope.core --cov=roomscope.models`, branch coverage):
**90.20 %** (0.4.0 on the same machine: 87.74 %, 345 tests); `ruff check`,
`ruff format --check`, `mypy` (strict, 69 files, with and without the
PySide6 stubs), `check_src_safety.py`, `check_doc_links.py`,
`build_docs_site.py`, `build_license_bundle.py`; `uv build` of sdist and
wheel (the wheel carries the hashed `.mo`, the sdist only the `.po`) and an
install of that wheel; a Linux PyInstaller 6.22.3 one-directory build from
`requirements/bundle.lock`, which has no `qml/` directory, passes
`check_bundle_contents.py --strip --require-licenses` and
`smoke_bundle.py` (`--version`, fake-backend measurement, offscreen GUI),
and runs a `--lang zh_CN` fake measurement from the `.po` without writing a
`.mo`. An independent review of the patch found a regression in the first
version of the #12 settling fix and two over-strict refusals in #10; they
were fixed before the pull request and are covered by tests. **What was
not run here:** CI on macOS / Windows and Python 3.14 (the pull request's
CI is the record), a macOS or Windows bundle, any hardware cell.

Snapshot 21: 2026-09-24 — **v0.4.0, first pre-release.** Milestones 0.2,
0.3, 0.4 and the 1.0-rc software were reviewed and merged into `main`
(PRs #5–#8; review follow-ups are issues #9–#16, listed in
[RELEASE_PLAN.md](RELEASE_PLAN.md) §6). The release commit adds the
verbatim LGPL-3.0 / GPL-3.0 / PortAudio texts to the license bundle and
the `--strip` bundle gate that also catches `Qt6`-prefixed and versioned
library names; the version-driven release workflow could not be pushed
from the preparing session (no `workflow` permission) and is delivered to
the maintainer (RELEASE_PLAN.md §3). **What was run
for this snapshot:** the new gate and license-bundle tests (9 tests) on
Linux x86_64 / Python 3.11 in a scratch layout; `ruff check` and
`ruff format --check` on the changed files; the numpy macOS wheels were
opened to establish the Accelerate-vs-OpenBLAS layouts. **What was not
run here:** the full suite and mypy on the release commit (CI runs them;
the last full local run is the 339/340 count of snapshot 20 on Linux),
any bundle build (the release workflow builds them), any hardware cell.
The zh-CN catalog covers three of seven profiles (#14); the earlier
"findings translated" wording was an overclaim and is corrected in the
CHANGELOG.

Snapshot 2: 2026-09-22 — recording profiles (vocal, voice-over, acoustic
guitar, drums, room mic, choir) added on top of the foundation; same
verification policy.

Snapshot 3: 2026-09-22 — developer-facing GitHub foundation (CI, issue/PR
templates, code of conduct, security policy). Re-verified on Linux x86_64
(Ubuntu, Python 3.12.3). The `gui` extra now installs PySide6_Essentials
only.

Snapshot 5: 2026-09-22 — v0.2 reopen and compare: Tier 1 lazy exports,
lenient loaders, shipped JSON Schemas, `compare()` / CLI / GUI, and
comparison findings. Hardware validation is still not claimed.

Snapshot 6: 2026-09-22 — 0.2 follow-up after CI on `0ad2a4e`: the
comparison test now requires the ISO 3382-1 "not significant" disclaimer
instead of forbidding the word "significant", and the wheel `force-include`
lists each schema JSON file so `roomscope/schemas/__init__.py` is not
added twice. Re-verified on Linux x86_64 (Ubuntu, Python 3.12.3).

Snapshot 7: 2026-09-22 — v0.3 trust the chain: loopback compensation,
`AudioBackend` + fake backend, progress and Stop, robustness tests, CI
OS matrix, hardware matrix started. Hardware cells are not marked PASS.
Re-verified on Linux x86_64 (Ubuntu, Python 3.12.3).

Snapshot 8: 2026-09-22 — v0.4 for everyone: gettext + zh-CN, self-contained
sessions and bundles, user settings, projects/averaging (SHOULD), CSV
export, user guide, unsigned-bundle pipeline (`release.yml`, license
bundle, GPL-module gate). Hardware cells are not marked PASS.

Snapshot 20: 2026-09-22 — macOS wheel audit: the wheel-audit test still
failed on the macOS runner. The diagnosis recorded at the time ("RECORD
omitted numpy's hidden `.dylibs/` folder") was wrong; the actual cause,
found on 2026-09-24, is that numpy's `macosx_14_0_arm64` wheel links Apple
Accelerate and bundles no shared library at all (DEPENDENCIES.md §6). The
`_on_disk_natives` merge in `audit_installed` is harmless and stays.
Hardware cells empty.

Snapshot 19: 2026-09-22 — M7 CLI output + README §6.4:
remaining CLI messages (sweep next steps, devices table,
measure/progress, error prefixes, argparse -h/--version) go
through gettext. README names the 1.0 platform set and that
anything else may work and is not tested. Hardware cells empty.

Snapshot 18: 2026-09-22 — wheel-audit test is OS-aware:
macOS/Windows CI failed because the Linux OpenBLAS+quadmath /
empty-ASIO checks ran against installed wheels. The test now
follows DEPENDENCIES.md §6 per platform; `.dylibs/` counts as
a bundled-lib folder. Hardware cells empty.

Snapshot 17: 2026-09-22 — 1.0-rc M7 CLI help / text-report labels:
`--lang zh_CN` translates CLI `--help` and every text-report
heading (ARCHITECTURE_V1.md §5.6). Windows win_amd64 wheels of
numpy/scipy/soundfile/matplotlib/Pillow opened (OpenBLAS +
msvcp140 / libsndfile; no ttconv; Pillow codecs are inside the
`.pyd` files). API/schema not frozen. Hardware cells empty.

Snapshot 16: 2026-09-22 — 1.0-rc M7 chrome / M9 wheel audit:
Linux x86_64 wheels of numpy/scipy/soundfile/sounddevice/
matplotlib/Pillow opened (`scripts/audit_wheel_contents.py`);
Windows sounddevice 0.5.6 wheel listed (ASIO DLLs still a
gate). DAW/Standalone/Results chrome goes through gettext.
API/schema not frozen. Hardware cells empty.

Snapshot 15: 2026-09-22 — 1.0-rc compare / robustness / guide:
`load_comparison` (findings re-derived on `roomscope show
comparison.json`); Compare GUI lists matched resonances; user
guide names every Results tab plus wrong-reference and
multiple-pass troubleshooting; robustness covers comparison.json,
more WAV/sidecar cases, and a microphone used as loopback;
`roomscope gui --smoke` is the §6.2 offscreen bundle smoke.
API/schema not frozen. Hardware cells empty.

Snapshot 14: 2026-09-22 — 1.0-rc §8 / M9 packaging remainder:
JSON depth cap, shared untrusted-file reader, src safety script,
unsigned zip/tar/dmg/Inno scaffolding and bundle smoke (fake
measure). API/schema not frozen. Hardware cells empty.

Snapshot 13: 2026-09-22 — 1.0-rc S7 / §5.8 remainder: themed docs
site from `docs/`, dark-mode plot and Qt chrome, device rate next to
the requested rate with `check_sample_rate` before Standalone
measure, compare reflections / loopback / MAD, Help → licenses.
API/schema not frozen. Hardware cells empty.

Snapshot 12: 2026-09-22 — 1.0-rc GUI/supply-chain: keyboard shortcuts
for File and Measure actions, linestyle-coded plots, Actions pinned
by SHA. API/schema not frozen. Hardware cells empty.

Snapshot 11: 2026-09-22 — 1.0-rc quality gates: docs link check, 85 %
coverage on `core`/`models`, `docs/index.md` hub, fixtures README.
API/schema not frozen. Hardware cells empty.

Snapshot 10: 2026-09-22 — 1.0-rc software on top of 0.4: Placement tab
(S5), Python 3.14 in CI (S6), M11 validation protocol with pre-chosen
tolerances, bundle.lock, SBOM/checksums and a trusted-publishing job
that still needs the maintainer `pypi` environment. Re-verified on
Linux x86_64 (Ubuntu, Python 3.12.3): 308 passed. Hardware cells are
not marked PASS. The repository is not public.

Snapshot 9: 2026-09-22 — 0.4 follow-up after the first local suite: `--json`
prints JSON again (deprecation on stderr, not `warnings.warn`); license
discovery follows files under `.dist-info/licenses/`; macOS
`NSMicrophoneUsageDescription` and the audio-input entitlement are in
`packaging/macos/`. Re-verified on Linux x86_64 (Ubuntu, Python 3.12.3).

## Implemented

| Area | What exists |
| --- | --- |
| Excitation | ESS generation (Farina), fades, level, silences; WAV + JSON sidecar; 44.1–192 kHz |
| Inverse filters | Analytic (time-reversed, −6 dB/oct) and regularised spectral division |
| Deconvolution | Whole-recording linear convolution; automatic IR location; pre-peak margin / confidence; sweep-start estimate |
| Reverberation | Schroeder integration, Lundeby truncation + compensation, EDT/T20/T30 with ISO 3382-1 ranges, validity flags, non-linearity, curvature, B·T check; broadband + octave bands 63 Hz–8 kHz (time-reversed Butterworth) |
| Frequency response | FFT with optional gating; raw kept; configurable fractional-octave smoothing |
| Background noise | Quiet-segment selection (pre-sweep / tail), RMS + peak dBFS (AES17), octave-band levels, Welch PSD, 50/60 Hz hum candidates |
| Early reflections | ETC peak candidates (delay ms, level dB re direct) with local-trend prominence |
| Placement geometry | Excess path per candidate; with a tape-measured loudspeaker distance the exact product of perpendicular distances and its two-sided bracket; with a microphone height the vertical axis (loudspeaker height, plane above the devices, horizontal separation). No coordinates, no room length or width, no wall named |
| Low-frequency resonances | Candidate peaks (< 300 Hz) with narrow-band decay vs. filter ringing comparison |
| Models & storage | Validated settings; result model with JSON export and `from_dict` load; MeasurementSession; self-contained session directory (session.json, result.json, IR WAV, optional recording.wav, always-copied sweep sidecar); `load_measurement` / `load_comparison` / `list_sessions` / `bundle_session`; recent list and `settings.json` under `$ROOMSCOPE_HOME`; shipped JSON Schemas; `comparison.json` (findings not stored); `project.json` |
| Interpretation | Finding model (`message_id` / `params` / `locale`); messages through gettext `_()`; RecordingProfile registry + entry points; seven profiles; `interpret_comparison` |
| CLI | `roomscope sweep / analyze / analyze-ir / show / compare / schema / devices / measure / gui / session bundle / export / project`; global `--lang`, `--format`, `--backend`, `--copy-recording` |
| Public API | Lazy Tier 1 exports from `import roomscope` (ARCHITECTURE_V1.md §5.1) |
| Loopback | Optional electrical return: pulse validation (99 % energy settling over the valid record, net of noise), regularised compensation with the FIR peak as time origin and linear division, path-delay bound; refused room-like or clipped channels leave the analysis uncompensated |
| Audio backends | `AudioBackend` protocol; PortAudio callback stream (progress polled from the waiting thread, Stop, callback errors and early stream end fail the take, buffer problems logged); `plan_input_channels` (1-based inputs → 0-based columns, validated before playback); fake backend for CI and Demo |
| Averaging | `average_decay`: VALID T values only; ISO 3382-2 class from 4.3.1 Table 1 (combinations, source and microphone positions all checked); `project average` counts distinct position labels |
| Export | CSV exporter for decay, FR, noise PSD, reflections, resonances; `roomscope.exporters` entry points |
| i18n | stdlib gettext with `pgettext` contexts; `zh_CN` catalog for report labels, GUI chrome, CLI help, the safety warning and the findings of all seven profiles (a test requires a translation with matching placeholders for every extracted message); wheel ships a hashed `.mo`, nothing is written at run time; `--lang` / settings / `ROOMSCOPE_LANG` |
| GUI | PySide6 window: Home, Universal DAW Mode, Standalone Mode, Results (including Placement), session save/open, Compare (difference curve, matched reflections and resonances, loopback deltas), Demo, Stop, Settings, project-folder browser, tape-measure fields, dark-mode plot chrome, device rate vs requested rate, `gui --smoke` |
| Standalone Mode | Device enumeration and play+record through the selected backend with safety defaults |
| Bundles | `scripts/build_license_bundle.py` (verbatim LGPL-3.0 / GPL-3.0 / PortAudio texts from `packaging/licenses/`), `scripts/check_bundle_contents.py` (`--strip`, `--require-licenses`, `--installed-essentials`; GPL-only QML module directories matched, any `qml/` tree in a frozen bundle fails), `packaging/roomscope.spec`, `release.yml` (the version-driven workflow that opens a draft Release is delivered to the maintainer for installation, see RELEASE_PLAN.md §3; the committed workflow is still the earlier tag-only one), `scripts/smoke_bundle.py` |
| Documentation | Hub at `docs/index.md`; themed HTML site from `scripts/build_docs_site.py` (S7); release plan in `docs/RELEASE_PLAN.md` |

## Tested (all PASS on 2026-09-17 on macOS; profile work re-verified 2026-09-22;
Linux x86_64 re-verified 2026-09-24 for v0.4.1, snapshot 22)

```
pytest      470 passed  (tests/unit 366, tests/integration 54, tests/ui 12 offscreen, tests/robustness 38)
coverage    90.20 % of roomscope.core + roomscope.models (branch; gate 85 %)
ruff check  All checks passed  (src, tests, examples, scripts)
ruff format files already formatted
mypy        Success: no issues found in 69 source files (strict)
```

The count above is the full local run of snapshot 22 (Linux, CPython
3.12.3). The previous full local run was 339 tests (snapshot 20); the
v0.4.0 tree gives 345 tests and 87.74 % coverage on the same machine.

The 2026-09-17 macOS log recorded 256 tests. Later DSP work replaced a
peak-normalised inverse with unit in-band gain and consolidated some
assertions; the two loopback tests that still expected a time-domain peak
of 1.0 were updated on 2026-09-22 and pass on Linux. Session-reopen tests
(result `from_dict`, `load_measurement`, recent list, `roomscope show`,
GUI re-open) plus the 0.2 compare / schema / Tier 1 lock tests brought
the suite to 259. 0.3 added loopback, the backend protocol and robustness
tests (283). 0.4 adds i18n, settings, bundles, averaging, CSV, license
gates and the macOS microphone plist (301). 1.0-rc adds the Placement
tab, the validation-protocol test and the bundle-lock test (304), then
the docs-link and fixtures tests (308), then shortcuts, plot
linestyles and Action SHA pins (311), then the themed docs site,
dark-mode plot chrome, device-rate display and compare tables (316),
then JSON depth, src-safety and unsigned-bundle packaging (322),
then comparison load/show, resonance table, richer robustness and
`gui --smoke` (334), then the Linux wheel audit and DAW/Standalone
gettext chrome (336), then CLI help / text-report labels and the
Windows wheel listing (338), then remaining CLI output
gettext and the README platform statement (339).
GUI tests also check that
matplotlib's QtAgg backend loads against PySide6_Essentials (no Addons).

What the tests prove with synthetic signals (no real-room recording is used
as evidence):

* Sweep instantaneous frequency follows `f1·exp(t/L)` (2 % tolerance);
  levels, fades, silences and lengths are exact; all six sample rates work;
  invalid settings are rejected.
* Sweep ⊛ inverse filter is a band-limited pulse with **unit in-band
  magnitude** (0 dB median over the normalisation band, analytic and
  spectral). The time-domain peak is about `2·bandwidth/fs` (~0.82 at
  48 kHz), not 1.0; everything outside ±2 ms is below −35 dB re that peak.
* Loopback recording → IR peak matches `reference_pulse()` at the expected
  index; delay and gain are recovered; too-short, silent and tail-less
  recordings raise clear errors; clipping is warned.
* Exact exponential decay → EDT/T20/T30 within 1 %; noisy exponential decays
  (RT60 0.25/0.6/1.2 s) within 5 %; octave-band T30 within 10 %; a 30 dB
  decay range yields `insufficient_decay_range` for T20/T30 (no number);
  B·T < 4 is flagged unreliable; Lundeby cross-point lands near the noise
  crossing.
* Frequency response of a delta is 0 dB flat; comb-filter notch/peak depths
  are exact; smoothing preserves constants and reduces spikes.
* Full-scale sine = 0 dBFS RMS (AES17); 60 Hz hum with harmonics is detected
  and 50 Hz is not; white noise triggers no hum.
* Discrete reflections at 18/35 ms with −9/−15 dB are found within 0.1 ms
  and 0.5 dB, also in a band-limited IR with a diffuse tail.
* A ringing 62 Hz mode is reported as a distinguishable resonance candidate;
  a flat response yields none.
* Recording profiles: all seven profiles produce findings with measured
  evidence on a rich synthetic room; voiceover flags a weaker reflection than
  generic; vocal flags a decay that room_mic accepts; drums skips noise
  findings; each profile names its recording kind; CLI `--profile` selects
  the profile and rejects unknown names (added 2026-09-22).
* End-to-end: RT60 0.45 s, reflection 18 ms/−9 dB and noise −77 dBFS are
  recovered from a synthetic room; recordings at 44.1 and 96 kHz against a
  48 kHz sweep definition; stereo channel auto-selection and explicit
  selection; WAV-only reference (spectral inverse) and resampled reference;
  loudspeaker distortion (2nd/3rd order) leaves the linear IR clean; CLI
  round trip incl. JSON; session save/load/re-open (`load_measurement`,
  `roomscope show`, GUI File → Open and Home recent/browse); two synthetic
  positions compare with a validity on every decay delta and a noise delta
  that stays UNRELIABLE until `same_input_gain` is declared; `roomscope
  schema` matches the shipped files; the Tier 1 export list matches
  ARCHITECTURE_V1.md §5.1; a synthetic interface FIR is removed to within
  1.0 dB median in-band error; a room-like loopback is refused; Stop on
  the fake backend zeroes the next callback block; `roomscope --backend
  fake measure` completes a Standalone session; GUI DAW-mode, Demo and
  pick-two compare offscreen.
* Bundle gates (2026-09-24): the GPL gate rejects `QtCharts.abi3.so`,
  `libQt6QuickTimeline.so.6`, `Qt6VirtualKeyboard.dll` and a
  `QtCharts.framework` binary, ignores `.pyi` stubs and the stock
  Essentials `Qt/lib`, `Qt/plugins`, `Qt/qml` trees in
  `--installed-essentials` mode, and `--strip` removes the offenders and
  leaves `libQt6Widgets.so.6` in place; the license bundle ships the
  verbatim LGPL-3.0, GPL-3.0 and PortAudio texts and reports them as
  unresolved when PySide6 is installed and the texts are missing.
* Review follow-ups (2026-09-24, v0.4.1): the bundle gate reports and
  strips the virtual-keyboard / timeline QML plugins of the real
  Essentials 6.11.2 tree by directory and rejects any QML tree in a frozen
  bundle (#17); every message extracted from `src/` has a zh-CN
  translation with matching placeholders and four profiles print no
  English finding text under `--lang zh_CN` (#14); a 31-tap linear-phase
  interface no longer moves the compensated sweep start (5.000 ms before,
  within one sample now), a clean loopback with a 1.5–12 s post-roll and
  60 dB peak-to-noise is accepted, and a close microphone in a live room
  (RT60 1.5 / 4 s) is still refused (#12); progress is reported from the
  waiting thread, callback exceptions and early stream ends fail the take,
  Stop on a stalled device returns after the 0.5 s grace period instead of
  the timeout, a loopback on the microphone input is refused before
  playback (#13; scripted `sounddevice` stand-in, not hardware); two takes
  that differ only in the diffuse tail compare at 0.79 / 0.38 / 0.24 dB MAD
  in the 4 / 8 / 16 kHz octaves (3.30 / 2.81 / 2.44 dB before), and a
  +6.02 dB shelf is recovered within 0.3 dB (#9); a re-imported
  `impulse_response.wav` reproduces the
  sweep analysis (RT60 ±1 %, reflection ±0.05 ms / ±0.2 dB, resonance),
  declared sub-woofer IRs are accepted and noise / sweep files are refused
  (#10); session members outside the
  folder, absolute or via symlink, are refused (#11); the ISO 3382-2 class
  matrix and the project position count follow Table 1 (#15); the safety
  script catches aliases and dynamic imports (#16).
* macOS basic run: `roomscope sweep`, `roomscope analyze`,
  `roomscope devices` (12 Core Audio devices listed), the example script,
  and the GUI (offscreen) ran successfully. **Not run:** a real Standalone
  measurement through loudspeakers/microphone (needs a person in the room to
  set levels) and the on-screen GUI on a display.

**Not run:** no placement result has ever been checked against a real room
with a tape measure. Every placement figure in the test suite comes from
arrivals synthesised by the image-source construction, so the tests prove the
algebra and the refusals, not the acoustics of any real surface.

## Known limitations

* A single session does not reach the ISO 3382-2 "survey" class (Table 1
  needs two microphone positions). `average_decay` means VALID T values
  across a project's positions and names the Table 1 class (read from the
  standard's preview pages; its footnotes and the other clause 4
  conditions are not checked). Decay curves are never averaged.
* Direct sound = strongest deconvolved sample; a reflection stronger than the
  direct sound would be mis-identified (confidence margin does not catch it).
* PortAudio buffer under/overflows are logged, not refused; whether a real
  interface reports them, and whether Stop and an unplugged device behave
  as the scripted stand-in does, is unverified (hardware matrix).
* Loopback validation and compensation have synthetic evidence only.
* An imported impulse response that starts at its peak cannot be checked
  for being an IR and is analysed with direct-sound confidence "low".
* Below about 1 kHz a frequency-response comparison of two positions
  mostly shows real modal differences (2–4 dB MAD for two diffuse
  realisations of the same synthetic room), not a change of treatment.
* Band filters are Butterworth, not certified IEC 61260 class 1; short
  decays in the 63/125 Hz bands are limited by B·T and are flagged.
* Lundeby parameters (20 ms initial blocks, 5 intervals/10 dB, 7.5 dB
  margins) are RoomScope's choices within the published ranges; other tools
  will differ slightly.
* Reflection and resonance outputs are candidates; in dense diffuse tails
  some reflection candidates are statistical; room modes are not identified.
* Noise levels are dBFS only; no SPL calibration; mains-hum thresholds are
  engineering choices.
* No clock-drift correction between separate playback and recording
  devices (Universal DAW Mode relies on the DAW/interface clocking).
* `result.json` with curves is several MB for long IRs (`--no-curves` to
  shrink); the raw IR WAV is the authoritative record.
* zh-CN: core diagnostics (`warnings`, `notes`, `reason`) and plot titles
  stay English by design; the Chinese text was written by the project, not
  reviewed by a second translator.
* The GUI is functional but plain. Session re-opening, a folder/recent
  list, a two-session comparison, Settings, Demo/Stop, a `project.json`
  folder view and a Placement tab (S5) are in. There is no large session
  database.

## Not implemented (by design for v0.1 or deferred)

VST3/AU/AAX plug-ins, room score, auto-EQ/correction, cloud/accounts, 3D
room modelling, absorption material calculators, dB SPL, room-mode
identification, phase display, signed desktop installers. A themed
documentation site is generated from `docs/` (`scripts/build_docs_site.py`).
Unsigned bundles are built by `release.yml` when the version changes;
a person installing a frozen bundle on macOS/Windows is not claimed.

## Dependencies

Runtime: numpy 2.5.3, scipy 1.18.1, soundfile 0.14.0, sounddevice 0.5.6,
matplotlib 3.11.2; optional GUI extra `gui`: PySide6_Essentials 6.11.2
(Qt 6.11.2, LGPL; Addons not installed). Dev: pytest, pytest-cov, ruff,
mypy, jsonschema, hatchling (the build backend, listed for the build-hook
test). Full table with licenses: DEPENDENCIES.md.

## License status

RoomScope: Apache-2.0 (LICENSE verbatim from apache.org, NOTICE present;
rationale in LICENSE_DECISION.md). All runtime dependencies are permissive
or LGPL used dynamically; no copyleft obligation reaches RoomScope's source.
Obligations that apply to a *binary* distribution (Qt LGPL texts and
notices, libsndfile LGPL, FreeType credit, PortAudio/Qhull/Agg notices,
Windows ASIO DLL removal, GPL-only Qt module removal) are listed in
DEPENDENCIES.md §3–§4 and are enforced by `build_license_bundle.py` and
`check_bundle_contents.py --strip --require-licenses` in the release
workflow. They must be re-checked whenever a dependency version changes.

## Third-party provenance

No third-party source files vendored (CODE_PROVENANCE.md). Twenty-one
external repositories were audited (THIRD_PARTY_REVIEW.md); all were used as
conceptual references only. GPL projects (DRC, Aliki) and proprietary REW
were not copied. `packaging/licenses/` holds verbatim license *texts*
(LGPL-3.0, GPL-3.0, PortAudio), not code.

## Known licensing risks

* Frozen desktop builds are unsigned until the maintainer holds signing
  identities; the license bundle now carries the Qt / PySide6 texts and
  Qt stays a set of replaceable shared libraries.
* PySide6_Essentials 6.9+ wheels ship GPL-only Qt libraries
  (`libQt6QuickTimeline.so.6`, the virtual-keyboard and timeline QML
  plugins) that RoomScope never imports; the release workflow strips them
  from every bundle and the gate fails if one survives, or if a frozen
  bundle contains a QML tree at all (#17). A local Linux PyInstaller build
  contained none of them.
* Windows sounddevice wheels contain ASIO DLLs built with the proprietary
  Steinberg SDK — stripped by the same step.
* numpy's macOS wheels differ by deployment target (Accelerate on
  `macosx_14_0`, OpenBLAS + libgfortran/libquadmath on `macosx_11_0`); the
  license bundle for a macOS build must be generated on the build machine
  (DEPENDENCIES.md §6).
* Two in-force patents adjacent to the field (US 9,959,883; US 10,816,391)
  are noted in MEASUREMENT_METHODOLOGY.md §10 so the design does not drift
  into them. Not a legal opinion.

## Next recommended milestone

See [RELEASE_PLAN.md](RELEASE_PLAN.md): v0.4.1 closes #9–#17 once its
pull request is merged with CI green; then v0.5.0 once the hardware
matrix has its first dated PASS rows, then 1.0.0rc1 when every MUST item of ARCHITECTURE_V1.md §3.1 is
closed. API and schema versions stay unfrozen until then.

Maintainer-only actions that this work does not do: public visibility flip,
publishing a GitHub Release (which creates the tag), a license change, or
rewriting published history.
