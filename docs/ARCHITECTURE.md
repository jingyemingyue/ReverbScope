# ReverbScope architecture

Status: v0.1 foundation (2026-09). This document describes what exists and the
extension points that later milestones (plug-ins, more profiles, calibrated
SPL) must respect.

The design for v1.0 -- the first release open to everyone -- is a separate
proposal, [ARCHITECTURE_V1.md](ARCHITECTURE_V1.md) (Chinese digest:
[ARCHITECTURE_V1.zh-CN.md](ARCHITECTURE_V1.zh-CN.md)). It only adds to what is
described here; the dependency direction and the single analysis entry point
are unchanged.

## 1. Goals that shape the architecture

| Goal | Consequence |
| --- | --- |
| DAW-independent | The only interface to a DAW is a WAV file in each direction. No DAW SDK, ever. |
| Core-first | `reverbscope.core` is pure NumPy/SciPy. GUI, CLI, devices and file formats are separate packages that only *call* the core. |
| Scientific correctness | Every algorithm is implemented from a published method; every metric carries a validity flag. |
| Honest numbers | Levels are dBFS unless calibrated; metrics are `None` + reason when the data is insufficient. |
| Legal clarity | No vendored third-party code; dependencies and reference repositories are audited (see the other docs). |

## 2. Package layout

```
src/reverbscope/
  __init__.py            version + lazy Tier 1 re-exports
  errors.py              exception hierarchy (ReverbScopeError -> ...)
  logging_config.py      rotating log under $REVERBSCOPE_HOME
  settings.py            user settings (language, profile, backend, folders)
  i18n.py                gettext setup, locale selection, `_()`
  locale/                zh_CN/LC_MESSAGES/reverbscope.po
  models/                data only, no algorithms
    audio.py             AudioSignal (samples, sample_rate, channel selection)
    configuration.py     SweepSettings, AnalysisSettings (validated, immutable)
    result.py            AnalysisResult and sub-results, Validity enum, JSON export
    result_load.py       JSON → AnalysisResult (unknown keys ignored)
    session.py           MeasurementSession (metadata, paths, summary)
    comparison.py        ComparisonResult, MetricDelta, CompareSettings
    project.py           Project index (SHOULD)
    calibration.py       reserved CalibrationRecord
  core/                  pure DSP
    sweep.py             ESS generation, analytic + spectral inverse filters
    deconvolution.py     whole-recording deconvolution, IR location, confidence
    impulse.py           envelopes, dB helpers
    filters.py           octave bands, Butterworth SOS, time-reversed filtering, smoothing
    decay.py             Schroeder integration, Lundeby truncation, EDT/T20/T30
    frequency_response.py
    noise.py             quiet segment, dBFS, PSD, mains-hum detection
    reflections.py       early-reflection candidates
    placement.py         vertical geometry from reflections + tape measurements
    resonance.py         potential low-frequency resonance candidates
    compare.py           validity-aware comparison of two AnalysisResults
    loopback.py          electrical-return validation and regularised compensation
    averaging.py         spatial average of VALID T values (SHOULD)
    pipeline.py          Reference + analyze() + analyze_impulse_response()
  io/
    wav.py               soundfile-based read/write, sweep sidecar, load_reference
    session_store.py     save_measurement / load_session / load_measurement / list_sessions / bundle_session / save_comparison
    recent.py            recent session paths under $REVERBSCOPE_HOME
    jsonutil.py          size-capped JSON object reads
    project_store.py     project.json index
    exporters/           csv.py + reverbscope.exporters entry points
  schemas/               result / session / comparison / project / sidecar JSON Schemas
  audio/                 optional (needs PortAudio); Standalone Mode only
    backend.py           AudioBackend protocol, DeviceInfo, get_backend()
    devices.py           PortAudio enumeration
    portaudio.py         callback stream with progress and Stop
    fake.py              synthetic-room backend + make_rir
    playrec.py           compatibility wrapper around get_backend()
  interpretation/
    interpreter.py       Finding, Severity, interpret(), interpret_comparison()
    profiles.py          RecordingProfile protocol; seven profiles (generic, vocal,
                         voiceover, acoustic_guitar, drums, room_mic, choir)
    registry.py          built-ins + reverbscope.profiles entry points
  cli/
    main.py              argparse subcommands, errors, exit codes
    console.py           terminal layout: colour policy, symbols, widths, tables, progress
    render.py            every report and message (the GUI's "Full report" panes too)
    report.py            format_report / format_comparison_report: render.py as plain text
  demo.py                reverbscope demo: two simulated positions through the real pipeline
  ui/                    optional (needs PySide6)
    app.py, main_window.py, pages.py, results.py, plots.py, workers.py, state.py
    browser.py           session list (Home and Compare); project.json folders
    compare_view.py      two-session comparison
    settings_dialog.py   language, profile, backend, copy-recording
```

Dependency direction (arrows point at what may be imported):

```
ui / cli  -->  interpretation  -->  models
   |               |
   +--> io --------+--> core --> models
   |
   +--> audio (Standalone Mode only)
```

`core` never imports `io`, `audio`, `ui` or `cli`. `models` imports nothing
from the rest of the package except `errors`.

## 3. Data flow

```
SweepSettings ──generate_ess──▶ sweep WAV (+ .reverbscope-sweep.json sidecar)
                                     │  played by a DAW or by audio.playrec
                                     ▼
recording WAV ──read_wav──▶ AudioSignal ──select_channel──▶ mono float64
                                                               │
Reference (settings | signal) ──inverse_filter(_spectral)──▶ inverse filter
                                                               │
                                       deconvolve(recording, inverse) = h_full
                                                               │
                                     locate_impulse_response ──▶ IR (+ direct index, margins)
                                                               │
                ┌──────────────┬───────────────┬───────────────┼─────────────────┐
                ▼              ▼               ▼               ▼                 ▼
          analyze_decay  frequency_response  analyze_noise  early reflections  resonances
                └──────────────┴───────────────┴───────────────┴─────────────────┘
                                                               ▼
                                                        AnalysisResult
                                                               │
                                   interpret(result) ──▶ Findings (advice layer)
                                   save_measurement ──▶ session.json, result.json, IR WAV
                                   load_measurement  ◀── session directory (IR from WAV)
```

Key decisions:

* **Whole-recording deconvolution.** The recording is never trimmed by hand.
  Linear convolution with the inverse filter is shift-invariant, so the IR is
  simply located at the strongest peak of the deconvolved signal. The
  estimated sweep start feeds the noise analysis (pre-sweep silence).
* **Reference regeneration.** With the sidecar, the reference is regenerated
  analytically at the *recording's* sample rate, which is exactly what a DAW
  played when it resampled the test signal. Without a sidecar, the WAV is
  used with a regularised spectral inverse.
* **Validity is data, not UI.** `DecayMetric.validity` and `reason` are set in
  the core; the CLI and GUI only render them.
* **Interpretation is separate.** `interpretation` reads an `AnalysisResult`
  and never changes it. Profiles implement `RecordingProfile.interpret`.

## 4. Two workflows, one core

| | Universal DAW Mode | Standalone Mode |
| --- | --- | --- |
| Excitation | `io.wav.write_sweep_file` -> user's DAW | `audio.playrec.play_and_record` |
| Recording | WAV exported from the DAW | returned by PortAudio |
| Reference | sidecar JSON (or WAV) via `io.wav.load_reference` | the `SweepSettings` just used |
| Analysis | `core.pipeline.analyze` | `core.pipeline.analyze` |

## 5. Extension points

* **Plug-ins (VST3 / AU / AAX, later):** wrap `core` behind a host-specific
  shell; the shell must produce a WAV-equivalent buffer and call `analyze`.
  Nothing in `core` assumes files or devices.
* **Recording profiles:** add a class implementing `RecordingProfile` and
  register it in `interpretation.profiles._PROFILES`.
* **Calibration (later):** add an optional calibration object to
  `AnalysisSettings`; `noise.py` would then also report dB SPL. Until then all
  levels stay dBFS.
* **Other storage formats:** `MeasurementSession.to_dict`/`from_dict` and
  `AnalysisResult.to_dict`/`from_dict` are the serialisation points;
  `schema_version` is checked on load. Readers are lenient: unknown keys are
  ignored and logged. Writers stay strict: `to_dict` output is validated
  against the shipped JSON Schemas in the test suite. IR samples live in
  `impulse_response.wav`.
* **Multi-position measurements (ISO 3382-2 engineering/precision):** sessions
  are per position; `core/averaging.average_decay` averages T values, not
  decay curves, and names the ISO 3382-2 class the position counts reach.
* **Multi-position placement (deferred, with a constraint):** two microphone
  positions with a fixed loudspeaker make the geometry *exactly* determined
  (twelve equations, twelve unknowns). Exactly determined means a zero
  residual proves nothing about whether the arrivals were assigned to the
  right surfaces, so a two-position solve must never ship as "exactly
  determined, therefore trustworthy". Any future support needs a redundant
  third position, and the canonicalisation of mirror and permutation
  degeneracies must be designed before, not after, the solver — see
  MEASUREMENT_METHODOLOGY.md §7a and §9.

## 6. Error model

`ReverbScopeError` is the base. Front ends catch it and show the message;
anything else is a bug. Subclasses: `ConfigurationError` (also a
`ValueError`), `InvalidAudioError` / `SampleRateMismatchError`,
`AnalysisError` / `InsufficientDataError`, `AudioDeviceError` /
`AudioBackendUnavailableError`, `SessionError`.

## 7. Threading and safety

* The GUI runs `analyze` and playback/recording in `QThread` workers.
* `audio.playrec` opens a stream only for the measurement, scales the sweep
  to the requested dBFS level (default -20 dBFS), and requires an explicit
  acknowledgement above -12 dBFS. Nothing touches system volume or device
  configuration, except the opt-in `--coreaudio-set-rate`, which lets
  PortAudio set the macOS device's nominal rate (SECURITY.md).

## 8. Testing strategy

Synthetic rooms (`tests/conftest.py`) with known RT60, reflections and
noise floors give exact expectations: sweep formula checks, unit-pulse
inverse filters, loopback = unit impulse, RT60 recovery within 5-10 %,
insufficient-range flags at low SNR, hum detection, stereo/mono and
sample-rate handling, invalid-file handling, CLI round trip, session
save/load/re-open, offscreen GUI smoke test (including reopening a saved
session). Real-room recordings are never the only evidence.
