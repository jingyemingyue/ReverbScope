# How ReverbScope compares

**English** | [简体中文](COMPARISON.zh-CN.md)

Last checked: 2026-09-24. Facts about other tools come from their own pages,
manuals and repositories (see *Sources*). Prices, editions and platforms
change, so check with the vendor. *Not documented* means we did not find the
point in those sources, not that the feature is missing. Corrections are
welcome as an issue or pull request.

## Who ReverbScope is for

ReverbScope is for recording engineers, students and home recordists who have
three questions about a room and a microphone position: *can I record here,
what is wrong with this position, and did moving the microphone or the
performer help?* ReverbScope measures, reports and compares. It does not correct
a monitoring system, simulate a room or tune a PA.

ReverbScope is a **pre-release (0.4.x)**. Synthetic tests cover its DSP on
Linux, macOS and Windows, but no result has yet been measured on real hardware
and checked against a reference instrument ([STATUS.md](STATUS.md),
[HARDWARE_TESTS.md](HARDWARE_TESTS.md)). Most tools below are mature products
with years of field use.

## What ReverbScope does differently

Other tools already do some of what follows. REW marks RT60 figures it
considers unreliable, Smaart falls back from T30 to T20 when the decay does
not clear the noise, and dual-channel analysers (Smaart, ARTA, Open Sound
Meter) use a reference channel. What ReverbScope adds is the combination, aimed
at recording positions, and a policy of refusing a number instead of guessing
one.

- **Every number has a unit, an algorithm source and a validity flag.**
  Field names carry the unit, and every metric's algorithm and literature
  reference are documented. Each metric is marked `valid`,
  `insufficient_decay_range`, `unreliable`, `outside_excitation_range` or
  `not_computed`. EDT, T20 and T30 need at least 20, 35 and 45 dB of decay
  range respectively (the ISO 3382 noise margin). With less, the report says
  *"Insufficient decay range"* and gives the measured range. Levels are
  dBFS; dB SPL would need a calibration, and 1.0 ships none. ReverbScope
  deliberately has no single "room score"
  ([MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md) §3, §9;
  `src/reverbscope/models/result.py`).
- **Two modes, one analysis pipeline.** In Universal DAW Mode, ReverbScope
  writes a sweep WAV, you play and record it in any DAW, and ReverbScope
  analyses the export. ReverbScope never talks to the DAW: there is no SDK and
  no plug-in. It finds the sweep anywhere in an untrimmed file, so you don't
  need to set a latency, and it reads Broadcast WAV, RF64, Wave64, AIFF, CAF
  and FLAC. In Standalone Mode, ReverbScope plays and records through an audio
  interface itself. Both modes call `reverbscope.core.pipeline.analyze`
  ([user-guide/daw-setup.md](user-guide/daw-setup.md)).
- **It explains a sweep the DAW played at the wrong speed.** When
  deconvolution fails, ReverbScope measures the sweep rate in the recording
  (a Theil–Sen fit of the sweep's time against log frequency). It then
  reports either a sample-rate mismatch ("a file generated at 48000 Hz was
  played at 44100 Hz") or a time-stretch (Warp, Flex, Follow Tempo). This is
  only a diagnosis: ReverbScope never re-analyses the recording at the measured
  speed (MEASUREMENT_METHODOLOGY.md §2b).
- **Recording profiles, labelled as interpretation.** The advice comes from
  a recording profile, never from the DSP. The profiles are generic, vocal,
  voiceover, acoustic guitar, drums, room mic and choir, and each has its own
  thresholds and wording. The report prints the profile name next to
  "Interpretation", so nobody mistakes the advice for a room-agnostic verdict
  (§8).
- **Placement geometry limited to what one microphone can measure.** From
  reflection delays, plus an optional tape-measured loudspeaker distance and
  microphone height, ReverbScope reports the loudspeaker height and the height
  of the surface above. It gives no coordinates, no room length or width, and
  never names a wall: one omni microphone at one position measures path
  lengths, not directions. When two arrivals could explain a value, both are
  listed and neither is picked (§7a).
- **Optional loopback compensation.** An electrical return of the interface
  output is checked first: it must behave like an electrical pulse. It then
  divides the interface's response out of the measurement and gives the
  electrical time origin. If the channel still carries room sound, ReverbScope
  rejects it, says why, and analyses without compensation (§2a).
- **Comparing sessions, with a validity on every delta.** A comparison of
  two positions answers "did moving help?". A decay delta exists only when
  both sides are valid, noise deltas need the input gain declared unchanged,
  and no change is called "significant" on the evidence of one pair (§11).
- **English and Simplified Chinese; Apache-2.0 with clean-room provenance.**
  Findings, the GUI, CLI help and the user guide are translated
  ([user-guide/zh-CN.md](user-guide/zh-CN.md)). Core diagnostic strings stay
  in English on purpose ([ARCHITECTURE_V1.md](ARCHITECTURE_V1.md) §5.6). All
  DSP was written from papers and standards. No third-party source code is
  included, and every repository studied during the design was
  license-audited ([CODE_PROVENANCE.md](CODE_PROVENANCE.md),
  [THIRD_PARTY_REVIEW.md](THIRD_PARTY_REVIEW.md)).

## Comparison table

"Through a DAW" means that a DAW or another recorder can play the test
signal and record the microphone, with the tool analysing the files. For
correction products, the column says where the correction runs.

| Tool | License / price model | Platforms | Primary purpose | Through a DAW / other recorder | Excitation / IR method | Reports metric validity |
| --- | --- | --- | --- | --- | --- | --- |
| **ReverbScope** | Apache-2.0, free | Windows 10/11 x64; macOS 14+ (arm64, x86_64); Linux x86_64; Python 3.12+ wheel | Measuring and interpreting recording positions | Yes: Universal DAW Mode (WAV out, WAV in); also Standalone | Exponential sine sweep, inverse-filter deconvolution; optional loopback; IR WAV import (`analyze-ir`) | Yes: a flag on every metric and every comparison delta; refuses a figure it cannot support |
| REW (Room EQ Wizard) | Proprietary freeware; paid Pro upgrade | Windows, macOS, Linux | Measurement and analysis; EQ filter design; room simulator | Yes: offline measurement. The REW sweep is played and recorded elsewhere, then loaded with *Import Sweep Recordings* (a timing reference is needed) | Log swept sine; stepped sine; RTA with noise | RT60: regression coefficient shown; figures it considers unreliable appear in orange italics; a Lundeby noise-floor estimate marks where the data stops being valid |
| Open Sound Meter | Desktop GPL-3.0, pay what you want; iPad app from the App Store | macOS, Windows, Linux; iPadOS | Real-time sound-system tuning | Not documented | Dual-channel FFT: RTA, magnitude, phase, impulse response, coherence, group delay | Coherence; reverberation metrics not documented |
| ARTA | Freeware since December 2024 (sales stopped March 2024) | Windows | IR, frequency-response and spectrum measurement; ISO 3382 room parameters | Drives the sound card itself; imports IR and signal WAV files; DAW playback not documented | Periodic noise, MLS, linear and log swept sine; single or dual channel | Correlation coefficient of the decay regression |
| Smaart (Rational Acoustics) | Commercial, perpetual or annual subscription; IR mode only in Smaart Suite | Windows 10 64-bit; macOS 10.14+ | Live sound-system tuning; IR mode with RT60 and STI | Live input needed; generator can play a WAV/AIFF file; opens WAV/AIFF impulse responses | Dual-channel transfer function plus inverse FFT, with pink noise or "pink sweep" (log sweep); single-channel recording for impulsive sources | Coherence for transfer functions; uses T20 when T30's end is not 10 dB above the noise floor; asks the user to check the automatic "saddle point" in each band |
| SoundID Reference (Sonarworks) | Commercial, perpetual tiers | macOS 11–15; Windows 10/11 | Speaker and headphone calibration (correction) | Correction runs as a DAW plug-in or system-wide; measurement in its own app | Frequency response of room and speakers with a measurement microphone; test signal not documented | Not documented (no room-acoustic metrics documented) |
| ARC X (IK Multimedia) | Commercial; free for registered owners of compatible IK hardware | macOS, Windows | Room correction for monitoring | Correction as a plug-in, in ARC Studio hardware or on-speaker DSP; measurement in its own app | 1-, 3-, 7- or 21-point measurement (VRM); test signal not documented | Not documented |
| Dirac Live | Commercial | Computer app; compatible AVRs and processors | Correction of impulse and frequency response (mixed-phase filters) | Correction on hardware or in computer audio; measurement in its own app | Impulse responses at several listening positions; test signal not documented | Not documented |
| HouseCurve | Free app with paid features | iOS, iPadOS | Measurement and EQ/FIR filter generation | Not documented | Sine sweep; real-time pink noise | "Automatic validation" of sweep measurements |
| AURORA (A. Farina) | "Published (not sold, nor licensed)" | Plug-ins for Adobe Audition 1.0–3.0; separate Audacity port | IR measurement, ISO 3382 parameters, auralisation | Yes: runs inside the audio editor | Log sine sweep | Not documented |
| pyroomacoustics | MIT, free | Python (pip) | Room simulation (image source, ray tracing); array processing | Not applicable; `experimental.measure_ir` plays and records through sounddevice | Simulated RIRs; experimental exponential/linear sweep with deconvolution; `measure_rt60` (Schroeder) | Not documented (`energy_thres` limits the fit on noisy tails) |
| python-acoustics | BSD-3-Clause; archived February 2024 | Python | General acoustics library (analysis) | Not applicable | Analyses signals it is given (for example T60 from an IR) | Not documented |
| pyrato (pyfar) | MIT, free | Python | Room-acoustic parameters from measured or simulated RIRs | Not applicable (analysis only) | Energy decay curves with noise handling (Chu subtraction, Lundeby) | Not documented |
| ITA-Toolbox (RWTH Aachen) | Open source (BSD-4-Clause per our audit) | MATLAB | Research toolbox: measurement, signal processing, ISO 3382 room acoustics | Uses its own playback and recording | Noise, sweep or MLS transfer function | ISO 3382-compliant noise-handling methods; per-metric flags not documented |

## When another tool is the better choice

- **EQ and room-correction filter design, waterfalls, room simulation.**
  REW finds response peaks automatically, assigns and optimises EQ filters
  for many hardware and software equalisers, and draws waterfalls and
  spectrograms. It also has a room simulator. ReverbScope designs no filters.
- **Correcting a monitoring system.** SoundID Reference, ARC X and Dirac
  Live measure in order to correct, and HouseCurve generates filters for
  hi-fi and home systems. ReverbScope only measures. To measure a corrected
  system with ReverbScope, keep the correction in the playback path on purpose
  ([user-guide/daw-setup.md](user-guide/daw-setup.md), item 3).
- **Live sound and real-time transfer functions.** Smaart and Open Sound
  Meter show live dual-channel FFT results with program material and
  coherence. ReverbScope works offline, one sweep at a time.
- **STI, strength and the rest of the ISO 3382 set.** REW Pro (STI), Smaart
  Suite (STI, clarity), ARTA and AURORA report speech transmission index,
  sound strength or lateral fractions. ReverbScope reports EDT, T20, T30,
  estimated RT60, and the single-position energy ratios C50, C80, D50 and
  centre time (methodology §3b). It does not report STI or strength G, and
  the ratios are not a room score.
- **Calibrated SPL or certified measurements.** ReverbScope reports dBFS only;
  its band filters are not certified IEC 61260 class 1, and one source and one
  microphone position do not reach the ISO 3382-2 survey class (methodology
  §3). ARTA can act as a virtual IEC class 1 SPL meter with a calibrated
  microphone, and Smaart has an SPL mode.
- **Room simulation and research scripts.** pyroomacoustics simulates rooms;
  pyrato and ITA-Toolbox compute room parameters in Python or MATLAB.
- **Results proven in the field today.** ReverbScope has no hardware
  validation yet. Until 0.5.0, treat its numbers as unvalidated.

## What ReverbScope deliberately does not do

Taken from [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md) §9 and
[ARCHITECTURE_V1.md](ARCHITECTURE_V1.md) §3.3:

- No room score.
- No auto-EQ and no room correction; correction filter design is densely
  patented (methodology §10).
- No dB SPL without calibration; every level in 1.0 is dBFS.
- No room-mode identification, only *potential* low-frequency resonances
  (methodology §7).
- No plug-in hosting, and no VST3/AU/AAX plug-in in 1.0.
- No room geometry beyond the vertical axis: no coordinates, no room length
  or width, no wall names. A room's full shape from echoes needs a microphone
  array or several positions; two positions would be exactly determined, so
  future multi-position support must add a redundant third.
- Spatial averaging combines T values only, never decay curves.
- No clock-drift estimation between separate playback and recording devices,
  and no automatic two-sweep scheme (both are covered by in-force patents).
- No cloud, accounts or telemetry.

## Sources

Accessed 2026-09-24. ReverbScope facts come from this repository: the files
linked above, and [research/reference_repos.md](research/reference_repos.md)
for the license audits it quotes.

- REW: [home page](https://www.roomeqwizard.com/), [features](https://www.roomeqwizard.com/features.html), [offline measurements](https://www.roomeqwizard.com/help/help_en-GB/html/offlinemeasurements.html), [RT60 graph](https://www.roomeqwizard.com/help/help_en-GB/html/graph_rt60.html), [RT60 decay graph](https://www.roomeqwizard.com/help/help_en-GB/html/graph_rt60decay.html), [EULA](https://www.roomeqwizard.com/eula.html)
- Open Sound Meter: [home page](https://opensoundmeter.com/), [repository (GPL-3.0)](https://github.com/psmokotnin/osm)
- ARTA: [home page](https://www.artalabs.hr/), [user manual](https://artalabs.hr/download/ARTA-user-manual.pdf)
- Smaart: [editions](https://support.rationalacoustics.com/support/solutions/articles/150000188536-which-edition-of-smaart-is-right-for-me-), [pricing](https://www.rationalacoustics.com/pages/smaart-v9-pricing), [system requirements](https://www.rationalacoustics.com/pages/smaart-v9-minimum-system-requirements), [Smaart v8 user guide](https://downloads.rationalacoustics.com/documentation/smaart-v8/Smaart-v8-User-Guide.pdf)
- SoundID Reference: [product page](https://www.sonarworks.com/soundid-reference), [pricing](https://www.sonarworks.com/soundid-reference/pricing)
- ARC X: [product page](https://www.ikmultimedia.com/products/arcx/)
- Dirac Live: [room correction](https://www.dirac.com/products/room-correction), [Wikipedia: Digital room correction](https://en.wikipedia.org/wiki/Digital_room_correction)
- HouseCurve: [home page](https://housecurve.com/)
- AURORA: [home page](https://www.aurora-plugins.com/index.htm)
- pyroomacoustics: [repository](https://github.com/LCAV/pyroomacoustics), [measure_ir](https://pyroomacoustics.readthedocs.io/en/pypi-release/pyroomacoustics.experimental.measure_ir.html), [measure_rt60](https://pyroomacoustics.readthedocs.io/en/pypi-release/pyroomacoustics.experimental.rt60.html)
- python-acoustics: [repository](https://github.com/python-acoustics/python-acoustics)
- pyrato: [repository](https://github.com/pyfar/pyrato), [documentation](https://pyrato.readthedocs.io/en/latest/modules/pyrato.html)
- ITA-Toolbox: [home page](https://www.ita-toolbox.org/), [measurement and room-acoustics paper](https://www.ita-toolbox.org/publications/ITA-Toolbox_paper4.pdf)
