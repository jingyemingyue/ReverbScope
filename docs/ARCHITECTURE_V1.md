# RoomScope v1.0 architecture (design)

**English** | [简体中文](ARCHITECTURE_V1.zh-CN.md)

Status: **proposal, 2026-09-22**, written for the maintainer's review.
[ARCHITECTURE.md](ARCHITECTURE.md) describes what exists (the v0.1
foundation). This document describes what v1.0 -- the first release that is
open to everyone, not only to developers -- adds, what it freezes, and what it
still refuses to do. Nothing below is implemented unless it is marked
*(landed)* or *(in PR #2)*. A Chinese digest is in
[ARCHITECTURE_V1.zh-CN.md](ARCHITECTURE_V1.zh-CN.md); the English text is
authoritative.

Decisions only the project owner can take are marked **maintainer decision**
and collected in §13. The scope table in §3 is the contract: an item that is
not MUST there is not a v1.0 blocker.

## 0. Summary

v0.1 proved the measurement chain on synthetic rooms and gave developers a
repository they can clone, test and review. "Open to everyone" means the same
chain in the hands of people who will never install Python, contributors who
will never touch the DSP, and integrators who read `result.json` from another
program. v1.0 therefore adds, in this order of importance:

1. **A frozen contract.** A named public Python API, versioned JSON file
   formats with shipped schemas, and a CLI whose JSON output is stable for the
   whole 1.x line (§5.1, §5.2, §5.7).
2. **The third product question.** v0.1 answers "is this room usable?" and
   "what is wrong at this position?". v1.0 answers "did moving the microphone
   or the performer help?" with a validity-aware comparison of two sessions
   (§5.3.2). The comparison is derived from two results and never changes
   either.
3. **A trustworthy chain.** An optional loopback (reference) channel divides
   out the audio interface's response and gives the electrical time origin,
   which turns the "interface latency is unknown" caveat of the placement
   geometry into a measured bound (§5.3.1).
4. **Standalone Mode for everyone.** An audio-backend interface with a fake
   backend for tests and a demo mode, multi-channel capture, progress and an
   immediate stop (§5.4).
5. **Their language.** Interpretation findings, the GUI and the CLI are
   translatable through gettext; Simplified Chinese ships first (§5.6).
6. **Installable artifacts.** Wheels on PyPI, and signed desktop bundles for
   macOS, Windows and Linux built by a release workflow that also produces the
   license bundle the LGPL/FreeType/PortAudio obligations require (§6).
7. **Evidence before the number 1.0.** A real-room validation campaign against
   a reference instrument, cross-platform CI, a hardware test matrix and
   robustness tests for untrusted files are release gates, not follow-ups (§7).

Everything the project brief forbade stays forbidden: no room score, no
auto-EQ, no plug-ins, no cloud, no accounts, no telemetry, no dB SPL without a
calibration, no room coordinates (§3.3).

## 1. Who "everyone" is

| Audience | What v1.0 gives them | What they must never need |
| --- | --- | --- |
| Recording engineers, students, home recordists | A signed desktop app; the four-step DAW workflow and Standalone Mode; a user guide in English and Chinese; a comparison of two positions; a session folder they can send when asking for help | Python, a terminal, an account, an internet connection, a calibrated microphone |
| Integrators and researchers | `pip install roomscope`; a public API with a stability promise; `result.json`, `session.json`, `comparison.json` with JSON Schemas; CSV export of every curve; `roomscope analyze-ir` for impulse responses from other tools | Reverse engineering the JSON; importing private modules |
| Contributors | A package layout where profiles, exporters and locales plug in without touching the DSP; cross-platform CI; ADRs that say why things are the way they are; a validation data set as regression evidence | A DSP background to add a profile or a translation; maintainer approval to run the full test suite locally |
| Translators and educators | gettext catalogs with message identifiers, so a finding can be translated once and stays translated when thresholds change | Editing Python |

## 2. Principles

Unchanged from v0.1 and the brief: DAW-independent (WAV in, WAV out),
core-first (`roomscope.core` is pure NumPy/SciPy), scientific correctness
(published methods, validity flags), honest numbers (dBFS unless calibrated,
no score), legal clarity (no vendored code, audited dependencies), safety
(conservative levels, nothing touches system audio settings).

Added for v1.0:

* **Compatibility is a feature.** Every file written by any 1.x version is
  readable by every later 1.x version. Readers are lenient (unknown keys are
  ignored and logged), writers are strict (validated against the shipped
  schema in the test suite). A breaking format change bumps the schema
  version and ships a migration, never a silent reinterpretation.
* **A session is self-contained.** A session folder carries everything needed
  to re-analyse it and to report a bug: the sweep definition, the raw
  recording (copied on request), the impulse response, the result and the
  metadata. Findings are derived data and are re-derived on load, never
  stored as truth.
* **Offline by construction.** The package contains no network code; CI fails
  if `socket`, `urllib`, `http`, `requests` or `ssl` are imported under
  `src/`. Update checks, crash upload and telemetry are out of scope for 1.x,
  not merely off by default.
* **Extension without forking.** Recording profiles, exporters and locales are
  discovered through entry points and catalogs; a third party can ship a
  profile pack as its own PyPI package.
* **Cancel is a safety control.** Any operation that drives a loudspeaker can
  be stopped at once from the UI, and stopping silences the output before
  anything else happens.

## 3. Scope of v1.0

### 3.1 MUST (release blockers)

| # | Item | Why it is a blocker | Section |
| --- | --- | --- | --- |
| M1 | Public API tiers and `roomscope` top-level exports *(landed in 0.2)* | Integrators cannot depend on a moving target | §5.1 |
| M2 | JSON Schemas for result, session, comparison, sweep sidecar; read-lenient loaders; `AnalysisResult.from_dict` *(landed in 0.2)* | Re-opening, comparing and exporting all need to read what was written | §5.2 |
| M3 | Session re-opening and a session browser *(landed in 0.2; started in PR #2)* | A tool that cannot show yesterday's measurement cannot compare positions | §5.8, §5.9 |
| M4 | Comparison of two sessions (core, CLI, GUI, interpretation) *(landed in 0.2)* | The third product question of the brief | §5.3.2 |
| M5 | Loopback reference channel (DAW export with two channels; Standalone two-channel capture) *(landed in 0.3)* | Removes the interface response from the frequency response and gives the electrical time origin; the largest known bias of the chain | §5.3.1 |
| M6 | Audio backend interface, fake backend, progress, immediate stop *(landed in 0.3)* | Standalone Mode logic must be testable in CI and safe on real hardware | §5.4 |
| M7 | Internationalisation framework with a Simplified Chinese catalog for findings, GUI and CLI *(landed in 0.4)* | "Everyone" includes the project's own first audience | §5.6 |
| M8 | Self-contained sessions, bug-report bundles, user settings *(landed in 0.4)* | Support without a screen-share | §5.9, §5.10 |
| M9 | PyPI release with trusted publishing; desktop bundles for macOS, Windows and Linux with the license bundle and the GPL-module gate | Nobody outside the project installs from git | §6 |
| M10 | Cross-platform CI, robustness tests for untrusted files, hardware test matrix executed at least once per platform | The public will run it on hardware the maintainer does not own | §7 |
| M11 | Real-room validation campaign published with its data | The methodology's claims have only synthetic evidence today | §7.4 |
| M12 | User guide (measure, read, compare, troubleshoot) in English and Chinese *(landed in 0.4)* | A signed binary without a guide produces wrong measurements | §6.5 |
| M13 | Public-repository checklist executed *(maintainer decision)* | The release is open only if the repository is | §9.1 |

### 3.2 SHOULD (planned; slips do not block 1.0)

| # | Item | Section |
| --- | --- | --- |
| S1 | `roomscope analyze-ir`: analyse an impulse response WAV from another tool *(landed in 0.3)* | §5.3.3 |
| S2 | Spatial averaging of T values over several sessions of one room (ISO 3382-2 style, with the accuracy class named) *(landed in 0.4)* | §5.3.4 |
| S3 | Project folders (one room, several positions) with a project view in the GUI *(landed in 0.4)* | §5.9 |
| S4 | CSV exporter for every curve; exporter entry points *(landed in 0.4)* | §5.7 |
| S5 | Placement tab in the GUI (the text report already has the section) *(landed in 1.0-rc)* | §5.8 |
| S6 | Python 3.14 in the CI matrix *(landed in 1.0-rc)* | §7.1 |
| S7 | Documentation site generated from `docs/` *(landed in 1.0-rc: hub at docs/index.md; `scripts/build_docs_site.py`)* | §6.5 |

### 3.3 Not in 1.0 (by design, or deferred with a stated reason)

* **Plug-ins (VST3 / AU / AAX).** Not needed for DAW independence (WAV is
  the interface) and legally different from the rest of the project: the
  VST3 SDK is dual-licensed (GPLv3 or a proprietary agreement), AAX requires
  an Avid agreement that an open repository cannot satisfy. A later plug-in
  shell must talk to the Apache-2.0 core across a process boundary designed
  for that purpose; the boundary itself is post-1.0 and needs a license
  review first (§11).
* **Clock-drift estimation or correction between separate playback and
  recording devices.** Outside the single full-duplex interface that
  RoomScope assumes, and the subject of an in-force patent (US 10,816,391 B2,
  MEASUREMENT_METHODOLOGY.md §10). The loopback channel of §5.3.1 uses one
  device and one clock and does not estimate drift.
* **Automatic two-sweep pass-band schemes** (US 9,959,883 B2). One sweep, as
  today.
* **dB SPL.** The calibration slot is reserved in the models (§5.3.5) but no
  calibration workflow ships in 1.0; every level stays dBFS.
* **Multi-position placement geometry.** Needs a redundant third position and
  the degeneracy canonicalisation described in MEASUREMENT_METHODOLOGY.md
  §7a and §9; not designed yet.
* **Room score, auto-EQ or correction, room-mode identification, 3D room
  models, absorption calculators, cloud, accounts, telemetry, update checks.**
  Unchanged from the brief.

## 4. Target package layout

Additions are marked `+`, changed modules `~`; everything unmarked stays as in
v0.1. `roomscope.core` keeps its single entry point `pipeline.analyze` and
gains three pure functions (`loopback.compensate`, `compare.compare`,
`averaging.average_decay`) with the same rules: NumPy in, dataclasses out, no
I/O, no Qt.

```
src/roomscope/
  __init__.py            ~ version + lazy re-exports of the Tier 1 API (§5.1)
  __main__.py            + `python -m roomscope` (needed by the desktop bundles)
  errors.py                exception hierarchy (unchanged)
  logging_config.py      ~ also writes a rotating log file under ROOMSCOPE_HOME for bug reports
  settings.py            + user settings (language, default profile, backend, folders) (§5.10)
  i18n.py                + gettext setup, locale selection, `_()` (§5.6)
  locale/                + <lang>/LC_MESSAGES/roomscope.po (+ .mo built at packaging time)
  schemas/               + result.schema.json, session.schema.json, comparison.schema.json,
                           project.schema.json, sweep-sidecar.schema.json (package data)
  models/
    audio.py               AudioSignal
    configuration.py     ~ SweepSettings; AnalysisSettings + loopback_channel, calibration slot
    result.py            ~ + LoopbackResult; roomscope_version; from_dict (in PR #2)
    result_load.py         (in PR #2) JSON -> AnalysisResult
    comparison.py        + ComparisonResult, MetricDelta, ReflectionMatch, ...
    session.py           ~ MeasurementSession + recording_profile (PR #2), roomscope_version,
                           platform, loopback metadata; lenient from_dict
    project.py           + Project (one room), PositionEntry
    calibration.py       + CalibrationRecord (reserved slot, no workflow in 1.0)
  core/
    sweep.py, deconvolution.py, impulse.py, filters.py, decay.py,
    frequency_response.py, noise.py, linearity.py, reflections.py,
    placement.py, resonance.py                            (unchanged)
    loopback.py          + reference-channel validation and regularised compensation
    compare.py           + validity-aware comparison of two AnalysisResults
    averaging.py         + spatial average of T values (SHOULD)
    pipeline.py          ~ analyze(): loopback step; analyze_impulse_response() (SHOULD)
  io/
    wav.py                 read/write, sidecar, load_reference (unchanged)
    session_store.py     ~ save/load; copy_recording; bundle(); list_sessions (PR #2)
    recent.py              (in PR #2) recent sessions under ROOMSCOPE_HOME
    project_store.py     + project.json and the sessions/ index (SHOULD)
    exporters/           + csv.py; entry-point group "roomscope.exporters" (SHOULD)
  audio/
    backend.py           + AudioBackend protocol, DeviceInfo, get_backend()
    portaudio.py         ~ the sounddevice backend (today's devices.py + playrec.py), stream
                           based, with progress and cancel
    fake.py              + synthetic-room backend for tests and the GUI demo mode
  interpretation/
    interpreter.py       ~ Finding + message_id/params/locale; interpret_comparison()
    profiles.py          ~ RecordingProfile + interpret_comparison; messages via _()
    registry.py          + built-ins + entry-point group "roomscope.profiles"
  cli/
    main.py              ~ + analyze-ir, compare, session, export, --format, --lang
    console.py           + terminal layout: colour policy, symbols, widths, tables, progress
    render.py            + every report and message (also the GUI's "Full report" panes)
    report.py            ~ plain-text wrappers over render.py (kept for existing imports)
  ui/
    app.py, main_window.py, pages.py, results.py, plots.py, workers.py, state.py, qt.py
    browser.py             (in PR #2) session browser
    compare_view.py      + two sessions side by side + difference plots
    settings_dialog.py   + language, default profile, backend, folders
```

Dependency direction (arrows point at what may be imported):

```
ui / cli ──▶ interpretation ──▶ models ◀── core
   │              │                          ▲
   ├──▶ io ───────┴──────────────────────────┘
   ├──▶ audio (backend protocol; portaudio only when a backend is requested)
   └──▶ settings, i18n
```

`core` never imports `io`, `audio`, `ui`, `cli`, `settings` or `i18n`; every
string it produces stays English and is stored verbatim in `result.json`
(§5.6 explains why). `models` imports only `errors`. `i18n` imports nothing
from the package.

## 5. Component designs

### 5.1 Public API and stability tiers

| Tier | What | Promise for the 1.x line |
| --- | --- | --- |
| 1 -- public | The names exported by `roomscope/__init__.py` (below); the JSON files and their schemas; `roomscope <cmd> --format json`; the CLI exit codes | Semantic versioning. Removal or a changed meaning needs a major version; additions are minor; a deprecation is announced with a `DeprecationWarning` one minor release before the change |
| 2 -- documented | Functions of `roomscope.core.*` named in MEASUREMENT_METHODOLOGY.md; `roomscope.audio.AudioBackend`; `RecordingProfile` / `ProfileBase`; the entry-point groups | Signatures may gain keyword parameters with defaults; every change is in CHANGELOG.md; algorithmic changes are also in the methodology document |
| 3 -- internal | `roomscope.ui`, `roomscope.cli` internals, everything `_`-prefixed | None |

Tier 1 exports, loaded lazily through a module-level `__getattr__` so that
`import roomscope` stays cheap and does not import SciPy, PortAudio or Qt:

```python
__version__
analyze, analyze_impulse_response, Reference            # core.pipeline
compare, ComparisonResult                               # core.compare, models.comparison
SweepSettings, AnalysisSettings                          # models.configuration
AnalysisResult, Validity, DecayResult, BandDecay, DecayMetric,
FrequencyResponseResult, NoiseResult, ReflectionsResult, Reflection,
ResonanceResult, PlacementResult, LoopbackResult         # models.result
MeasurementSession, Project                              # models.session, models.project
interpret, interpret_comparison, Finding, Severity, available_profiles
read_wav, write_wav, write_sweep_file, load_reference     # io.wav
save_measurement, load_measurement, load_session, list_sessions   # io.session_store
RoomScopeError and its subclasses                        # errors
```

The text report (`cli/render.py`) is *not* an interface: its wording is
localised and may change in any release. A test asserts that the Tier 1 list
in `__init__.py` and the list in this document match, and a second test that
`roomscope.__version__` equals the `pyproject.toml` version.

### 5.2 Schemas and file formats

**Versioning.** `result.json`, `session.json`, `comparison.json`,
`project.json` and the sweep sidecar each carry an integer `schema_version`.
The integer is bumped only for a change that a 1.0 reader could
misinterpret (a renamed key, a changed unit, a changed time origin). Adding
an optional key is not a bump. All v1.0 files are therefore schema 1 unless an
audit during the release-candidate phase finds a v0.1 key whose meaning
changed; v0.1 sessions remain readable either way.

**Readers are lenient, writers are strict.** `MeasurementSession.from_dict`
today refuses unknown fields; in v1.0 every `from_dict` ignores unknown keys
and logs them at INFO, refuses a *higher* `schema_version` than it knows
with a message naming the RoomScope version that can read it, and applies
registered migrations for lower versions. `to_dict` output is validated
against the shipped JSON Schema in the test suite (dev dependency
`jsonschema`, MIT, to be recorded in DEPENDENCIES.md), never at runtime.

**Shipped schemas.** `src/roomscope/schemas/*.schema.json` are package data,
hand-maintained (no code generation, no pydantic: the dataclasses stay the
source of truth and a test proves each dataclass round-trips through its
schema). `roomscope schema result` prints the current schema so integrators
can validate without cloning.

**What is stored where.**

| File | Content | Authoritative for |
| --- | --- | --- |
| `impulse_response.wav` (float32) | The located impulse response | The measurement (curves are recomputable from it) |
| `result.json` | Every metric with unit, validity and reason; curves unless `--no-curves`; `sweep_settings`, `analysis_settings`, `roomscope_version`, `warnings` | Numbers as they were reported |
| `session.json` | Metadata, paths, `analysis_summary`, `recording_profile` *(PR #2)*, `roomscope_version`, `platform`, loopback channel used | Provenance |
| `recording.wav` (copied, optional) | The raw recording, untouched | Re-analysis |
| `sweep.roomscope-sweep.json` (copied) | The sweep definition | Re-analysis |
| `comparison.json` | Two session references and the deltas | A comparison as reported |
| `project.json` | Room name, notes, list of position entries and their session folders | The index; sessions remain standalone |

Findings are not stored. Loading a session re-runs `interpret` with the
stored `recording_profile` and the running RoomScope version, and the report
names both, so advice always comes from the thresholds the reader can look
up, never from a frozen sentence.

### 5.3 Core additions

#### 5.3.1 Loopback reference channel (M5)

*Setup.* One interface output drives the loudspeaker and is also returned
electrically into a second input (a cable from an output to an input, or the
interface's own loopback). In Universal DAW Mode the user records the
microphone and the loopback on two tracks and exports either a two-channel
WAV or two files; in Standalone Mode RoomScope records both inputs in one
stream. Nothing changes for users without a loopback: every step below is
skipped and the result says `"loopback": null`.

*Inputs.* `AnalysisSettings.loopback_channel: int | None` (0-based channel of
the recording) or `analyze(..., loopback=AudioSignal)` for a separate file;
with a separate file, `loopback_channel` names a channel of that file instead.
The two signals must have the same sample rate and, for a separate file, the
same length within the recording-start tolerance; otherwise
`InvalidAudioError`.

*Validation before use (all in `core/loopback.py`).* The deconvolved
loopback `h_lb = rec_lb ⊛ inv` must be an electrical pulse: a single pass,
pre-peak margin in the "high" band of `confidence_label`, no clipping, and
its energy after the peak must fall to the noise floor within a few
milliseconds. A channel that decays like a room (the user routed the
microphone twice) or that is silent is refused with a note, and the analysis
continues uncompensated with `LoopbackResult.compensation_applied = False`
and the reason.

*Compensation.* In the frequency domain,
`H_room = H_mic · conj(H_lb) / (|H_lb|² + ε(f))`, with the regularisation
`ε(f)` small inside the excitation band and large outside it, so nothing
outside the band is amplified. This is the regularised inverse the project
already uses for reference WAVs (`design_spectral_inverse`), applied to the
loopback (Kirkeby et al. 1998; Müller & Massarani 2001 §"reference
measurement"; to be added to the references with their confirmation
status). The compensated `h_full` then goes through the unchanged
`locate_impulse_response` and the rest of the pipeline, so decay,
reflections, resonances and placement see the compensated response.
`FrequencyResponseResult.reference` reads
`"relative dB (0 dB = the interface loopback)"` when compensation was
applied.

*Time origin.* The loopback peak is the electrical time zero of the
playback-to-capture chain. `LoopbackResult.path_delay_ms` is the delay of the
microphone's direct sound relative to it, and
`distance_upper_bound_m = c · path_delay` is reported as a **bound**: the
electro-acoustic path may contain loudspeaker DSP latency, which only adds
delay, so the true loudspeaker-to-microphone distance is at most this value
and equals it only for a chain without digital latency. The tape-measured
`placement_distance_m` still drives the geometry; when it exceeds the bound,
the placement result is marked unreliable with that reason (the tape cannot
be longer than what sound had time to travel). This turns the "no absolute
time of flight" caveat of MEASUREMENT_METHODOLOGY.md §7a into a checked
quantity without claiming more than it proves.

*What it does not do.* No drift estimation or correction: both channels are
captured by the same converter clock. The loopback also does not remove the
loudspeaker's own response; RoomScope measures the room *through* the
loudspeaker and says so.

*Result model.* `LoopbackResult(channel, compensation_applied, reason,
latency_samples, path_delay_ms, distance_upper_bound_m,
interface_response_hz / interface_response_db (curves), notes)` under
`ImpulseResponseResult.loopback`; scalar copies in the session summary.

#### 5.3.2 Comparison of two sessions (M4)

`compare(baseline: AnalysisResult, candidate: AnalysisResult, *,
settings: CompareSettings | None = None) -> ComparisonResult` in
`core/compare.py`, pure, validity-aware, symmetric in what it refuses.

| Section | Rule | Output |
| --- | --- | --- |
| Comparability | Common excitation band = intersection of both bands; refused when it is narrower than one octave. Sample rates may differ. Different sweep durations or levels are allowed and noted | `comparable: bool`, `common_band`, `notes` |
| Decay (broadband and per band) | A delta exists only when *both* metrics are VALID; otherwise `NOT_COMPARABLE` with both reasons. Delta in seconds and in percent of the baseline. The report quotes the just-noticeable difference for T that ISO 3382-1 gives (about 5 %; clause to be verified against the standard text, as with the other clause references) and never calls a change "significant" on its own: single-position repeatability is not established by one pair | `MetricDelta(name, baseline, candidate, delta_s, delta_percent, validity, reason)` |
| Frequency response | Both smoothed curves interpolated onto a shared logarithmic grid inside the common band, with the same smoothing fraction (the coarser of the two); difference curve plus the mean absolute difference per octave band | `difference_db` curve, `band_mad_db` |
| Early reflections | Matched by delay within ±0.5 ms; level delta for matches; unmatched listed as appeared / disappeared. Requires high direct-sound confidence on both sides | `ReflectionMatch` list |
| Noise | RMS and band deltas are VALID only if both sessions have a verified quiet segment *and* the user declares the input gain unchanged (`CompareSettings.same_input_gain`); otherwise UNRELIABLE with the reason "gain not declared equal" | `MetricDelta` per band |
| Resonances | Matched within 1/6 octave; decay-distinguishable flags compared | `ResonanceMatch` list |
| Placement | Tier-2 heights compared when both present; refused otherwise | `MetricDelta` |
| Loopback | `path_delay_ms` compared when both compensated | `MetricDelta` |

The constants (±0.5 ms, 1/6 octave, one octave minimum) are `CompareSettings`
fields with these defaults and are documented in MEASUREMENT_METHODOLOGY.md
§11 when the module lands.

Interpretation: `RecordingProfile.interpret_comparison(comparison) ->
list[Finding]` with a shared implementation in `ProfileBase` that reuses the
profile's own thresholds, so "the strongest reflection within 30 ms went from
−8.7 dB to −14.2 dB" is judged with the same numbers the single-session
advice uses. CLI `roomscope compare <baseline> <candidate>`; GUI: select two
sessions in the browser (§5.8). Stored as `comparison.json` (schema 1) next
to the candidate session or wherever `--out` says.

#### 5.3.3 Impulse-response import (S1)

`analyze_impulse_response(ir: AudioSignal, settings, *, excitation_band:
tuple[float, float] | None = None) -> AnalysisResult` skips deconvolution,
sweep-position checks and distortion indicators, and runs decay, frequency
response, reflections, resonances and placement on the given response. The
excitation band is what the caller declares (`--band 20 20000`), recorded
with `source = "declared by the user"`; without a declaration the band is
marked unknown and every decay and energy metric, broadband included, is
`NOT_COMPUTED` with that reason. The noise section is `None` with the note
that no recording segment exists.
CLI `roomscope analyze-ir --ir <wav>`.

#### 5.3.4 Spatial averaging (S2)

`average_decay(results: Sequence[AnalysisResult]) -> AveragedDecay`:
arithmetic mean of EDT, T20 and T30 per band over the VALID metrics only,
with the count, the spread and the list of contributing sessions. Decay
curves are never averaged (ARCHITECTURE.md §5). The output names the ISO
3382-2 accuracy class the number of source and microphone positions
reaches; the class thresholds are transcribed from the standard's Table 1
when the module is written and go into MEASUREMENT_METHODOLOGY.md with their
confirmation status. Multi-position *placement* stays out (§3.3).

#### 5.3.5 Calibration slot (reserved)

`AnalysisSettings.calibration: CalibrationRecord | None = None` with
`CalibrationRecord(reference_dbfs, reference_db_spl, method, date, notes)`.
In 1.0 the field is accepted, stored in the session and ignored by the
analysis; the schema has the key so that a later minor release can report
dB SPL without a schema bump. `NoiseResult.calibration` keeps saying
"uncalibrated" until that release exists.

### 5.4 Audio backends (M6)

```python
class AudioBackend(Protocol):
    name: str

    def list_devices(self) -> list[DeviceInfo]: ...
    def check_sample_rate(self, device: int, sample_rate: int, *, kind: str) -> None: ...
    def play_and_record(
        self,
        playback: FloatArray,
        sample_rate: int,
        *,
        input_device: int | None,
        output_device: int | None,
        input_channels: Sequence[int],  # 1-based; [mic] or [mic, loopback]
        output_channel: int,
        level_dbfs: float,
        extra_record_s: float = 0.0,
        progress: Callable[[float], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> AudioSignal: ...  # shape (n, len(input_channels))
```

* `portaudio` (the existing sounddevice code) moves from a blocking
  `sd.playrec` to a callback `Stream`, so that `cancel` zeroes the output in
  the next callback and closes the stream, and `progress` reports the played
  fraction. Levels, the −12 dBFS acknowledgement and the safety message are
  unchanged.
* `fake` synthesises a room (the `make_rir` family from `tests/conftest.py`
  moves into `audio/fake.py` so the package does not import tests), records
  "through" it with a chosen noise floor, and honours `cancel` and
  `progress`. It backs the Standalone tests in CI and the GUI **Demo**
  mode, which lets someone without an interface see a complete measurement.
* Selection: `settings.audio_backend`, `ROOMSCOPE_AUDIO_BACKEND`, or
  `--backend`; `get_backend()` raises `AudioBackendUnavailableError` with the
  install hint when PortAudio is missing, exactly as today.
* No ASIO on Windows (the wheel's ASIO DLL is stripped from bundles, §6.2);
  WASAPI shared mode resamples when the device rate differs from the request,
  so `check_sample_rate` stays mandatory before a measurement and the GUI
  shows the device's current rate next to the requested one.

### 5.5 Interpretation (registry, messages, comparison)

* **Registry.** `interpretation/registry.py` merges the built-in profiles with
  `importlib.metadata.entry_points(group="roomscope.profiles")`. A
  third-party name that collides with a built-in is ignored with a warning;
  a profile that fails to import is reported, not fatal. `available_profiles()`
  lists both with their origin.
* **Contract for profiles** (unchanged in spirit, now written down): a
  profile reads an `AnalysisResult`, never changes it, states every threshold
  it applied in `Finding.evidence`, and never reports a number the result
  marked invalid.
* **Messages.** `Finding` gains `message_id` (a stable dotted identifier such
  as `reflection.strong_close`), `params` (the numbers and units the sentence
  uses) and `locale`; `message` is the sentence rendered through `_()` at
  interpretation time. `to_dict` emits all four. Profiles produce messages
  through `_()` with named placeholders, so translators translate a template
  once and a threshold change does not invalidate the translation.
* **Comparison findings.** `ProfileBase.interpret_comparison` (§5.3.2).

### 5.6 Internationalisation (M7)

* Mechanism: standard-library `gettext`. Catalogs live in
  `src/roomscope/locale/<lang>/LC_MESSAGES/roomscope.po`; `.mo` files are
  compiled by a Hatch build hook at packaging time and are not committed.
  Extraction and compilation use Babel (BSD-3-Clause, dev dependency; row to
  be added to DEPENDENCIES.md). English is the source language and needs no
  catalog.
* Selection: `--lang` / `settings.language` / `ROOMSCOPE_LANG`, otherwise the
  system locale; English when no catalog matches.
* What is translated in 1.0: interpretation findings, GUI chrome, CLI help
  and the labels of the text report, the user guide (zh-CN).
* What is deliberately **not** translated: the diagnostic strings produced by
  `roomscope.core` (`warnings`, `notes`, `reason` fields). They are stored in
  `result.json`, quoted in bug reports and compared across versions, so they
  must be identical whatever the UI language; the GUI shows them verbatim
  under a translated heading that says so. Revisiting this after 1.0 would
  require message identifiers inside the core and is recorded as a known
  limitation, not an oversight.
* Numbers keep ASCII digits and a decimal point in every locale; units are
  never translated.

### 5.7 CLI contract

| Command | Purpose | Status |
| --- | --- | --- |
| `sweep`, `analyze`, `devices`, `measure`, `gui` | as today | landed |
| `show <session>` / `show --list <folder>` / `show comparison.json` | print a stored session or comparison; list sessions | landed |
| `analyze-ir --ir <wav> [--band lo hi]` | analyse an impulse response from another tool | S1 |
| `compare <baseline> <candidate> [--out] [--same-input-gain]` | comparison | M4 |
| `session bundle <session> [--no-audio]` | zip for bug reports | M8 |
| `export <session> --format csv [--out]` | curves and tables through an exporter | S4 |
| `schema result\|session\|comparison\|project\|sidecar` | print the JSON Schema | M2 |
| `measure --input-channels 1,2 --loopback-channel 2`, `analyze --loopback-channel 1` / `--loopback <wav>` | loopback | M5 |
| global `--format text\|json`, `--lang <tag>`, `--backend <name>`, `--copy-recording`, `--color auto\|always\|never` | global options | M7, M6, M8 |

Exit codes: 0 success; 1 a `RoomScopeError` (message on stderr); 2 usage
error or a safety refusal (the level acknowledgement); 130 interrupted.
`--format json` writes exactly the `result.json` payload plus `findings` to
stdout and nothing else there; all diagnostics go to stderr. `--json` stays
as an alias for one minor release, then is removed with a warning.

Text output is laid out by `roomscope/cli/console.py` (styles, status
symbols, display-width-aware wrapping and tables) and `roomscope/cli/render.py`;
no other module writes escape sequences. Colour follows `--color`, then
`NO_COLOR`, then `FORCE_COLOR`, then `TERM=dumb`, and in `auto` appears only
on a terminal: a pipe or a file never receives an escape sequence or a
carriage return. Every status carries a symbol and a word (`✓` / `!` / `×` /
`→`, or `[OK]` / `[WARN]` / `[ERROR]` / `->` where the stream cannot encode
them), so colour is never the only signal; on such a stream the other signs
(`Δ`, `→`, `–`) are written in ASCII too, and a narrow terminal encoding
replaces what it cannot show instead of failing. Widths count a CJK character
as two columns; text is laid out for at most 100 columns.

Every command reads the same way: title and context, the result ("At a
glance" first in an analysis or a comparison), the detail, then numbered
next steps. A user error is one block (`× error: …`, an explanation, the
commands to try) with the documented exit code; a traceback appears only with
`--verbose`. Bare `roomscope` prints a short home screen on stderr and keeps
the usage error's exit code 2. `measure` prints its device plan and checks on
stdout and its progress on stderr (one redrawn line on a terminal, one stage
line otherwise; drawn by the waiting thread, never by the audio callback). The
text layout is not a Tier 1 interface. The GUI's "Full report" panes show the
same `render.py` reports as plain text; the environment report in the
developer tools keeps `diagnostics.format_environment_report`.

### 5.8 GUI

The GUI remains a PySide6 Essentials (LGPL) engineering tool with matplotlib
plots; QtCharts and every other GPL-only Qt module stay banned (§6.2 adds
an automated check).

* **Home:** New Measurement (two modes), Open Session, Browse Folder, recent
  sessions *(PR #2)*, **Demo** (runs Standalone Mode on the fake backend and
  says so on every screen).
* **Measurement pages:** loopback channel selection; a progress bar and a
  **Stop** button during playback (§2, §5.4); the device's actual sample rate
  next to the requested one.
* **Results:** the six tabs of today plus **Placement** (S5) and, when a
  loopback was used, the interface response on the Frequency Response tab.
  Core diagnostics appear verbatim under a translated heading (§5.6).
* **Compare:** pick two sessions in the browser; side-by-side tables with
  deltas and their validity, the difference curve, the matched reflections
  and resonances; the "input gain unchanged" declaration is an explicit
  checkbox because it decides whether the noise delta may be shown.
  `roomscope show comparison.json` re-derives findings (they are not stored).
* **Settings dialog:** language, default profile, audio backend, default
  output folder, copy-recording default.
* **Session browser / project view:** the browser from PR #2, extended to
  show a project's positions when the folder has a `project.json` (S3).
* Platform details that decide whether "everyone" can use it: keyboard
  navigation for every action, high-DPI scaling, the system dark mode, no
  information encoded in colour alone in the plots, the macOS microphone
  permission string in the bundle (§6.2).

### 5.9 Storage: self-contained sessions, projects, bundles (M8, S3)

```
<session>/                      unchanged files keep their names and formats
  session.json
  result.json
  impulse_response.wav
  recording.wav                 copied when --copy-recording / the GUI default (on)
  sweep.roomscope-sweep.json    always copied (tiny; makes the session re-analysable)

<project>/                      SHOULD
  project.json                  room name, notes, positions[]: {label, session_dirs[]}
  sessions/<UTC timestamp>-<position slug>/   ordinary session folders
```

* Paths in `session.json` stay relative when inside the folder; a session
  moved as a folder keeps working.
* `roomscope session bundle` zips the folder for a bug report; `--no-audio`
  leaves the WAVs out for people who do not want to share a recording of
  their room. The measurement issue template will ask for the bundle.
* `ROOMSCOPE_HOME` (default `~/.roomscope`, introduced by PR #2 for the
  recent list) holds recent sessions, the settings file and the log file.
  Nothing else is written outside the folders the user chose.

### 5.10 User settings

`roomscope/settings.py` reads and writes `ROOMSCOPE_HOME/settings.json`
(`schema_version`, `language`, `default_profile`, `audio_backend`,
`output_dir`, `copy_recording`). Plain JSON, written by the package's own
code, so the CLI does not depend on Qt and no configuration library is
added. Level acknowledgements are never persisted: the −12 dBFS confirmation
is asked on every measurement, as the brief's safety rules require.

## 6. Distribution (M9)

### 6.1 PyPI

* Project name `roomscope` (checked free on PyPI on 2026-09-22; registering
  it is a **maintainer decision** and should happen before the first
  pre-release so the name in this document stays true).
* Pure-Python wheel (`py3-none-any`) and sdist, built by `python -m build`
  as in today's `package` CI job, published through PyPI Trusted Publishing
  (OIDC from the release workflow; no long-lived token in the repository) to
  a GitHub environment that requires the maintainer's approval.
* Extras stay `gui` (PySide6 Essentials only) and `dev`; a new `i18n-dev`
  extra carries Babel. `pipx install "roomscope[gui]"` is the documented
  path for people who have Python but no interest in a virtual environment.
* `[project.gui-scripts] roomscope-gui = "roomscope.ui.app:main"` gives
  Windows a console-less launcher next to the `roomscope` console script.

### 6.2 Desktop bundles

* **Tool:** PyInstaller in one-directory mode (macOS `.app` inside a `.dmg`;
  Windows a zip and an Inno Setup installer; Linux an AppImage built on the
  oldest supported Ubuntu LTS runner). One-directory keeps Qt, libsndfile and
  libquadmath as separate, replaceable shared libraries, which is what the
  LGPL obligations in DEPENDENCIES.md §3 require. Alternatives considered in
  §11.
* **Architectures:** macOS arm64 and x86_64 as separate bundles (a
  universal2 bundle only if every wheel is universal2, which NumPy and SciPy
  are not); Windows x64; Linux x86_64. Others are community territory.
* **Bundle contents gate (CI, blocking):** the built bundle must contain no
  GPL-only Qt module (an allow-list of `QtCore`, `QtGui`, `QtWidgets`,
  `QtDBus` on Linux and their plugins; anything else fails the job), no
  `*asio*.dll`, and a `THIRD_PARTY_LICENSES/` directory produced by
  `scripts/build_license_bundle.py`, which extends today's
  `scripts/dependency_licenses.py`: license texts of every bundled wheel, the
  LGPL-3.0 and GPL-3.0 texts and the Qt / PySide6 source pointers, the Qt
  third-party attributions for the Essentials modules, the FreeType credit,
  the PortAudio license (not in the wheel), the Qhull and Agg notices. The
  About dialog links to that directory. The UNKNOWN / NEEDS REVIEW items of
  DEPENDENCIES.md §6 (matplotlib's `ttconv` is resolved; Linux x86_64
  and Windows win_amd64 wheels of numpy/scipy/soundfile/sounddevice/
  matplotlib/Pillow were opened on 2026-09-22; the Windows sounddevice
  wheel still ships ASIO DLLs)
  must stay current when those versions change; the license bundle
  script lists any package whose license file it could not find and
  fails the job.
* **Reproducible inputs:** bundles are built from a lock file
  (`requirements/bundle.lock`, generated with `pip-compile` or `uv` from
  `pyproject.toml`) so a bundle can be rebuilt from its tag; the library
  keeps its version ranges.
* **macOS:** `Info.plist` with `NSMicrophoneUsageDescription` (without it the
  system denies the microphone silently), hardened runtime, the
  `com.apple.security.device.audio-input` entitlement, Developer ID signing
  and notarization. **Windows:** Authenticode signing of the installer and
  the executable. Both need identities only the maintainer can hold
  (**maintainer decision**, §13); until they exist, bundles are published as
  *unsigned* with the Gatekeeper / SmartScreen steps in the user guide, and
  1.0 is not called 1.0 without at least the macOS notarization or an
  explicit maintainer decision to ship unsigned.
* **Smoke test:** every bundle is launched on its own runner
  (`roomscope --version`, `roomscope --backend fake measure` on the
  synthetic room, `roomscope gui --smoke` offscreen) before it is attached
  to a release. Nothing is sent to a loudspeaker.

### 6.3 Release workflow

`release.yml` runs on a `v*` tag pushed by the maintainer (tags stay
maintainer-only, as CONTRIBUTING.md says):

1. lint, type-check, full test matrix (§7.1);
2. sdist and wheel → PyPI (pre-releases such as `v1.0.0rc1` go to PyPI as
   pre-releases, so `pip install roomscope` never picks them up by accident);
3. bundles on the three OS runners → bundle gates → smoke tests;
4. `SHA256SUMS`, a CycloneDX SBOM (`cyclonedx-bom`, Apache-2.0, dev
   dependency to be recorded) and `THIRD_PARTY_LICENSES.zip`;
5. a **draft** GitHub Release with everything attached and the CHANGELOG
   section as its body; the maintainer publishes it.

Versioning: `pyproject.toml` is the single source; `roomscope.__version__`
is read from package metadata; a test proves both agree. Version numbers
follow SemVer; schema versions are independent integers (§5.2).

### 6.4 Supported platforms for 1.0

macOS 13+ (arm64, x86_64), Windows 10/11 x64, Linux x86_64 with glibc of the
build runner or newer, Python 3.12–3.14 for the wheel. Anything else is
"may work, not tested" and is stated as such in the README.

### 6.5 Documentation for users (M12, S7)

`docs/user-guide/` in Markdown, English with a Chinese translation:
installing (bundle, pipx), the DAW workflow with per-DAW notes contributed
by users, Standalone Mode and the loopback cable, reading each result tab
(what a validity flag means, why there is no score), comparing two
positions, troubleshooting (clipping, wrong reference, multiple passes,
device rates), and how to send a bug-report bundle. A generated site (S7)
is built by `scripts/build_docs_site.py` (stdlib Markdown subset, dark-mode
CSS); GitHub still renders the Markdown.

## 7. Quality gates (M10, M11)

### 7.1 CI matrix

* `lint`: ruff, ruff format, mypy strict, the no-network import gate (§2),
  the Tier 1 export test, the version test, link check on `docs/`.
* `test`: Ubuntu, macOS and Windows on Python 3.12; Ubuntu also on 3.13 and
  3.14 (S6). Full matrix on `main` and on tags; pull requests run the same
  jobs (nine minutes of runner time is cheaper than a platform bug found by
  a user). Every job runs the GUI smoke tests offscreen and the Standalone
  flow on the fake backend.
* `schemas`: every JSON the suite writes validates against the shipped
  schema; the schema files are byte-identical to `roomscope schema`.
* `package`: as today, plus an install of the wheel into a clean environment
  and `python -c "import roomscope; roomscope.analyze"`.
* `bundle` (on `main` and tags): §6.2 gates and smoke tests.

### 7.2 Test tiers

| Tier | Where | Evidence it provides |
| --- | --- | --- |
| Unit, synthetic | `tests/unit` | Algebra, formulas, refusals (as today) |
| Integration, synthetic | `tests/integration` | Round trips, loopback compensation of a synthetic interface response, comparison of two synthetic positions, averaging |
| GUI offscreen | `tests/ui` | Flows build and run; demo mode; compare view |
| Robustness | `tests/robustness` | Malformed WAV, JSON, sidecar, session and project files raise `RoomScopeError`, never anything else; oversized JSON is refused (size cap); truncated WAVs; NaN audio; a loopback channel that is actually a microphone |
| Fixtures, real | `tests/fixtures` (already whitelisted in `.gitignore`) | Short real recordings (a few seconds, contributed under CC0 with a written declaration in `tests/fixtures/README.md`) as *regression* evidence: the numbers must not drift between releases. Real recordings are never the only evidence for a change (CONTRIBUTING.md) |
| Hardware, manual | `docs/HARDWARE_TESTS.md` | The matrix of §7.3, filled in by hand, dated, with the RoomScope version |

Coverage is reported for every job and enforced only for `core` and `models`
(threshold chosen when the gate is introduced, then only raised).

### 7.3 Hardware test matrix

Executed at least once per platform before 1.0 (M10) and recorded in
STATUS.md with the date and the interface: device enumeration, sample-rate
negotiation at 44.1 / 48 / 96 kHz, channel mapping beyond channels 1–2,
loopback capture, Stop during playback, a full measurement in Standalone
Mode, and the same signal through one DAW per platform in Universal DAW
Mode. Community results are accepted through the measurement issue template
with a bundle attached.

### 7.4 Validation campaign (M11)

Before 1.0 the methodology's claims get real-room evidence, published as
`docs/VALIDATION.md` with the raw files (CC0, as release assets if too large
for the repository, with checksums):

* at least two rooms (one treated, one untreated), at least two positions
  each, one interface, one loudspeaker, one measurement microphone;
* the **same recorded WAV** analysed by RoomScope and by a reference
  instrument (Room EQ Wizard, used only as a comparison instrument and never
  copied; or an open MATLAB / Python toolbox with a clear license), which
  isolates the analysis from the acquisition;
* per-band T20 and T30, EDT, the strongest early reflection's delay, and the
  loopback-compensated frequency response compared, with the acceptance
  tolerance chosen and written down *before* the measurements (ISO 3382-2's
  stated repeatability, or an explicit engineering tolerance);
* every disagreement explained or turned into an issue. A campaign that
  fails its tolerance blocks 1.0 and is published anyway.

The placement geometry gets the check STATUS.md says has never happened: a
tape measure against `source_height_m` and `ceiling_height_m` in both rooms.

## 8. Security and privacy

* **Attack surface:** files the user opens (WAV through libsndfile, JSON
  through the standard library) and audio devices. Robustness tests (§7.2)
  cover the parsers; JSON loads are capped in size and depth; no `pickle`, no
  `numpy.load` with `allow_pickle`, no `eval`, no shell-outs.
* **Supply chain:** Dependabot (present) for pip and Actions; Actions pinned
  by SHA; a lock file for bundles; an SBOM per release; PyPI trusted
  publishing; release artifacts with checksums and, where identities exist,
  signatures.
* **Privacy:** every byte stays on the user's machine; sessions may contain
  room names, notes and recordings of a private space, so bundles support
  `--no-audio` and the issue templates say what a bundle contains before
  asking for one. No telemetry, no update check (§2).
* **SECURITY.md** at 1.0: supported versions = the latest 1.x minor; private
  vulnerability reporting enabled on the repository (**maintainer
  decision**); the safety rules for Standalone Mode unchanged.

## 9. Community and governance

### 9.1 Opening the repository (M13, maintainer decision)

The flip itself is one click; the checklist before it: description and
topics; branch protection on `main` (CI required, no force-push); a
`CODEOWNERS` file naming the maintainer for `src/roomscope/core`,
`docs/MEASUREMENT_METHODOLOGY.md` and the license documents; private
vulnerability reporting; labels (`good first issue`, `help wanted`, `dsp`,
`gui`, `packaging`, `i18n`, `profile`, `measurement`, `validation`);
Discussions enabled for measurement questions; the roadmap (§10) pinned as
an issue. Recommended timing: at the first release candidate, so the
candidate gets outside testing and the 1.0 release is not the first public
day.

### 9.2 How contributions scale without a DSP background

* **Profiles** and **translations** are the on-ramps: a new profile is a
  class, a registry entry and a synthetic test; a translation is a `.po`
  file. Both are labelled `good first issue`.
* **DSP changes** keep today's rules: a published source, a synthetic test
  with a known expectation, and a methodology entry.
* **Decisions** that change a Tier 1 or Tier 2 interface, a schema, a
  dependency or a method are recorded as an ADR in `docs/adr/` (one page:
  context, decision, alternatives, consequences). This document's decisions
  (§11) become ADR-0001 onwards when accepted.
* **Contribution terms:** Apache-2.0 §5 already governs contributions;
  requiring a DCO sign-off (`Signed-off-by`) is a **maintainer decision**.
* **Release cadence:** a minor release when a MUST or SHOULD item lands and
  CI is green on every platform; patch releases for fixes only.

## 10. Milestones and exit criteria

| Version | Theme | Content | Exit criteria |
| --- | --- | --- | --- |
| 0.2 | Reopen and compare | PR #2 (reopen, browser, `show`); `compare` core + CLI + GUI + comparison findings; lenient loaders; JSON Schemas and the schema CI job; Tier 1 exports and the export test | Any v0.1 session reopens; two sessions compare with every delta carrying a validity; `roomscope schema` matches the shipped files |
| 0.3 | Trust the chain | Loopback (DAW two-channel export, Standalone two-channel capture); `AudioBackend`, fake backend, progress and Stop; `analyze-ir`; cross-platform CI; robustness tests; hardware matrix started | A synthetic interface response is removed within a stated tolerance; Stop silences within one callback period on real hardware; the Standalone flow runs in CI on all three OSes |
| 0.4 | For everyone | i18n + zh-CN; self-contained sessions, bundles, settings; demo mode; projects and averaging (SHOULD); CSV exporter; user guide; unsigned bundles from `release.yml` on all three OSes with the license bundle and the GPL-module gate | A person without Python installs a bundle and completes the demo and a DAW measurement in Chinese or English; the license bundle lists no unresolved package |
| 1.0-rc | Freeze and prove | API and schema freeze; validation campaign published; hardware matrix complete; signed bundles or an explicit maintainer decision; SECURITY / CONTRIBUTING / STATUS updated; repository public; pre-release on PyPI | No open MUST item; every gate in §6–§7 green on the tag |
| 1.0 | Release | Fixes from the candidate only | Same gates; release notes name the validation results and the known limitations |
| post-1.0 | | dB SPL calibration workflow; multi-position placement with a redundant third position; a documented process boundary for plug-in shells (license review first); more locales; 1/3-octave decay bands; phase display; a documentation site | |

No dates: the exit criteria are the schedule.

## 11. Decisions and alternatives

| Decision | Chosen | Alternatives considered | Why |
| --- | --- | --- | --- |
| Desktop toolkit | Keep PySide6 Essentials + matplotlib | A local web UI (browser + local server); Tk; a Rust/Tauri shell | Exists, LGPL-clean, native file dialogs and audio permissions; the core boundary is unchanged, so a web front end remains possible later without touching `core` |
| Bundling | PyInstaller one-directory | Briefcase; Nuitka; py2app / cx_Freeze | Mature hooks for PySide6, SciPy and matplotlib; a predictable one-directory layout for the LGPL; revisit Briefcase if signing and notarization automation prove painful |
| Plug-in discovery | Entry-point groups (`importlib.metadata`) | Config-file paths; namespace packages | Standard library, pip-installable profile packs, no path handling in the UI |
| Internationalisation | gettext + Babel (dev only) | Qt Linguist `.ts` for the GUI only; hand-written JSON catalogs | One mechanism for CLI, GUI and findings; Linguist would split the catalogs and leave the CLI untranslated |
| Core diagnostics untranslated | English in `result.json`, verbatim in the UI | Message identifiers inside `core` | The strings are part of the stored record and of bug reports; adding identifiers to every core note is a large change with no measurement benefit; recorded as a limitation |
| Schemas | Hand-maintained JSON Schema files + round-trip tests; `jsonschema` in tests only | pydantic / msgspec models; generated schemas | No new runtime dependency; the dataclasses remain the source of truth; validation at write time in tests is enough for files the package itself produces |
| Settings storage | JSON under `ROOMSCOPE_HOME`, written by package code | `QSettings`; TOML (needs `tomli-w`); `platformdirs` | The CLI must not depend on Qt; no new dependency; one folder for everything the app writes outside the user's chosen output |
| Project index | `project.json` listing session folders | SQLite | Files are the truth; tens of sessions, not thousands; a project stays readable by hand |
| Comparison time origin | Direct sound of each result; the electrical zero when both have a loopback | Cross-correlation of the two responses | The direct sound is already the time origin of every decay figure; aligning on it keeps deltas explainable |
| Loopback compensation | Regularised division inside the excitation band | Time-domain deconvolution; no compensation, report the loopback separately | Reuses `design_spectral_inverse`; nothing outside the band is amplified; the uncompensated path remains the fallback |
| Audio backend | PortAudio via sounddevice behind a protocol; a fake backend | Native CoreAudio / WASAPI bindings; PyAudio | Cross-platform with one code path; the protocol makes the GUI and CLI testable and leaves room for native backends later |
| Minimum Python | 3.12 (unchanged) | 3.11 for wider reach | The code uses 3.12 syntax throughout; bundles carry their own interpreter |
| Curves in `result.json` | Keep JSON with `--no-curves`; CSV exporter for interop | NPZ sidecar; HDF5 | JSON stays readable without NumPy; the IR WAV is the authoritative record anyway |

## 12. Risks

| Risk | Effect | Mitigation |
| --- | --- | --- |
| No signing identities (Apple Developer ID, Windows certificate) | Bundles trigger Gatekeeper / SmartScreen warnings; adoption drops | Maintainer decision early (§13); unsigned builds documented; PyPI path unaffected |
| Hardware diversity (device rates, channel maps, exclusive modes, PipeWire) | Standalone Mode fails for some users | Backend protocol + hardware matrix + community results through the issue template; Universal DAW Mode as the always-working path |
| Validation campaign needs rooms, gear and time | 1.0 slips | It is a MUST and the reason 1.0 means something; the protocol is written first so others can run it |
| Users loop back the wrong channel | Compensation with a room response would corrupt every metric | The validation gates in §5.3.1 refuse a loopback that is not an electrical pulse |
| Translation drift as thresholds and wording change | Stale advice in one language | Message identifiers with parameters; the English template is the source; untranslated strings fall back to English |
| Scope creep | 1.0 never ships | §3 is the contract; SHOULD items slip without discussion |
| Patents adjacent to the field | Drift into a claimed method | The two in-force patents are named in §3.3; no drift correction between devices, no automatic two-sweep schemes |
| GPL Qt modules or ASIO DLLs entering a bundle | License obligations RoomScope cannot meet | The blocking bundle gate (§6.2) |
| PyPI name taken before registration | Renaming the package and every document | Register `roomscope` before the first pre-release |
| PR #2 and this design diverging | Two session models | PR #2 is the 0.2 baseline; this document only adds to it |

## 13. Maintainer decisions and open questions

1. **Public flip timing:** at 1.0-rc (recommended) or at 1.0?
2. **Signing identities and budget:** Apple Developer Program, a Windows
   code-signing certificate; or ship 1.0 unsigned with documentation?
3. **PyPI project name and ownership:** register `roomscope`; who holds the
   account; enable trusted publishing.
4. **Validation campaign:** which reference instrument, which rooms, who
   runs it; may REW be used as a comparison instrument (its EULA allows use,
   not redistribution or reverse engineering)?
5. **DCO sign-off:** require it or rely on Apache-2.0 §5 alone?
6. **Languages:** Simplified Chinese first; Traditional Chinese, Japanese,
   German next, or whatever translators arrive?
7. **Recording copy default:** copy the raw recording into every session by
   default (self-contained, larger folders) or only on request?

## 14. Changes to existing code implied by this design

Small, listed so that reviewers can see the blast radius:

* `MeasurementSession.from_dict`: ignore unknown keys (log at INFO) instead
  of raising; refuse only a higher `schema_version`.
* `AnalysisResult`: `roomscope_version` field; `ImpulseResponseResult.loopback`;
  `from_dict` *(PR #2)*.
* `AnalysisSettings`: `loopback_channel`, `calibration`.
* `Finding`: `message_id`, `params`, `locale`; profile messages through `_()`.
* `RecordingProfile`: `interpret_comparison`; `_PROFILES` behind
  `registry.py`.
* `audio/devices.py` + `audio/playrec.py` → `audio/portaudio.py` behind
  `AudioBackend`; `play_and_record` gains `input_channels`, `progress`,
  `cancel`; the blocking `playrec` call becomes a callback stream.
* `cli/main.py`: `--format`, `--lang`, `--backend`, `--copy-recording`,
  `--loopback-channel`; new subcommands; `--json` deprecated.
* `roomscope/__init__.py`: lazy Tier 1 exports; `__version__` from metadata.
* `save_measurement`: copy the sidecar always and the recording on request.
* `tests/conftest.py`: the synthetic-room helpers move to `audio/fake.py`
  and are imported from there.
* CI: OS matrix, schema job, no-network gate, bundle job; `release.yml`.
* Docs: MEASUREMENT_METHODOLOGY.md §11 (comparison), §2a (loopback),
  §3a (averaging); DEPENDENCIES.md rows for `jsonschema`, Babel,
  `cyclonedx-bom`, PyInstaller and Inno Setup (build-time tools, with their
  licenses); STATUS.md per milestone; `docs/adr/`; `docs/user-guide/`;
  `docs/VALIDATION.md`; `docs/HARDWARE_TESTS.md`.
