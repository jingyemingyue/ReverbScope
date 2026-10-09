# Release-readiness audit of the measurement path (0.5.0rc1)

> **Read with 0.5.0rc2.** This audit was made on the code of `0.5.0rc1`. rc2
> changed the decay, filter and sweep code afterwards (the rules for a
> response that is cut short, a step in the decay and an EDT far longer than
> the late decay; the settling cache; the sweep-rate guard) and added
> Measurement health, comparison verdicts and the dropout detector, which
> carry their own rows in `docs/MEASUREMENT_METHODOLOGY.md` §3 and §12; the
> audit below was not repeated for them.

Audited on 2026-10-06 against the code of the `0.5.0rc1` candidate (the
0.5.0b2 line). The question for each number ReverbScope reports is not
"does a test pass" but: **does the number travel with a validity,
confidence or reason, and is it withheld when the measurement cannot
support it?** The rule the candidate is held to: rather return
*unavailable*, *insufficient decay range*, *low confidence* or *invalid*
than a precise-looking value nobody measured.

Everything below was verified with synthetic signals, closed-form decays,
scripted device stand-ins and the fake backend. **None of it is hardware
evidence**; the last section says what only real equipment can settle.

## How a number carries its validity

| Carrier | Where | Values |
| --- | --- | --- |
| `Validity` + `reason` on every decay and energy metric | `models/result.py` (`DecayMetric`, `EnergyMetric`) | `valid`, `insufficient_decay_range`, `unreliable`, `not_computed`, `outside_excitation_range`; comparisons add `not_comparable`. A metric that is not `valid` keeps its number only as a diagnostic; the estimated RT60 and the curvature are dropped (`with_all_unreliable`). |
| Direct-sound confidence | `ImpulseResponseResult.direct_sound_confidence`, `pre_peak_margin_db` | `high` (margin ≥ 20 dB), `medium` (≥ 10 dB), `low` (less, or nothing before the peak to check). Low confidence marks every decay and energy metric unreliable. |
| Notes and warnings in the interface language | every result section, `AnalysisResult.warnings` | Stored in English as catalogued diagnostics; shown translated. A joined reason never loses its parts. |
| Refusal | `InvalidAudioError`, `ConfigurationError`, `AnalysisError` | Input that cannot be measured is refused with a sentence, never analysed into numbers. |

## Metric by metric

| Metric | Reported as | Withheld or marked when | Tests |
| --- | --- | --- | --- |
| EDT, T20, T30 | `DecayMetric` per band: seconds, `validity`, `reason`, non-linearity ξ; `rt60_estimate_s` with `rt60_basis` (T30, else T20, else none) | decay range below 20 / 35 / 45 dB (`insufficient_decay_range` with the numbers); unverified or rival direct sound, clipping, aliased distortion, wrong playback speed, device timing fault (`unreliable`, every metric of the take); B·T < 4 in a band; curvature or ξ beyond the straightness limits; a rejected Lundeby estimate that changes the fit by more than 5 %; a band outside the excitation range (`outside_excitation_range`, no number); no excitation band known for an imported response (`not_computed`) | `tests/unit/test_acoustic_oracle.py` (closed-form decays at eight sample rates, 0.1–10 s; silence, DC, noise and low SNR give no RT60), `tests/unit/test_decay.py`, `tests/integration/test_decay_validity.py`, `tests/integration/test_recording_checks.py` |
| C50, C80, D50, centre time | `EnergyMetric` per band: value, unit, `validity`, `reason` | decay range below 20 dB; truncation point before the early window; every take-level gate above; the split is the first sample at or after 50 / 80 ms, never a rounded one | `test_acoustic_oracle.py` (ratios against the integral of the envelope; sample 1102 vs 1103 at 22.05 kHz), `test_decay.py` |
| Direct sound (time zero) | `direct_sound_confidence`, `pre_peak_margin_db`, notes | margin below 20 / 10 dB; a separated earlier peak within 20 dB (`low`, metrics unreliable, time zero not moved); an imported file whose peak stands less than 10 dB above what precedes it is refused; a file that starts on its peak is `low` but still reports numbers, because nothing contradicts them | `tests/integration/test_analyze_ir.py` (rival arrival at 12 / 15 / 40 dB), `tests/unit/test_deconvolution.py` |
| Early reflections | candidates `(delay_ms, relative_db)`, the window actually searched, `window_truncated`, `direct_sound_confidence`, notes | low direct-sound confidence (candidates kept, note says delays are relative to a peak that may not be the direct sound); a response that ends inside the window is reported as truncated, not as "no reflections"; bounds inclusive; candidates are peaks, not identified surfaces, and the note says so | `tests/unit/test_reflections.py` (boundary arrivals at 44.1 / 48 / 96 kHz, out-of-window peaks, truncated windows) |
| Frequency response | curves with `excitation_band`, `resolution_hz` (of the gate, not the zero padding), `bin_spacing_hz`, `gated`, `reference` | outside the excitation band the curve is roll-off, leakage and noise, and the result says so; a gate longer than the response does not fade the direct sound; the resolution reported is that of the analysed time after the direct sound | `tests/unit/test_frequency_response.py`, `test_acoustic_oracle.py` (gain, polarity, NaN / Inf / zero rate refused) |
| Background noise, mains hum | `NoiseResult`: segment source, RMS / peak dBFS, per-band levels, PSD, hum candidates with their harmonics; `calibration` says dBFS, not dB SPL | no verified quiet segment, digital silence, or a level below the quantisation floor: the level is `None` and the note says why; a DC offset is not noise; a short segment reports no hum from one spectrum | `tests/unit/test_noise.py`, `tests/integration/test_recording_checks.py` |
| Potential resonances | candidates with frequency, level above baseline, narrow-band decay, filter ringing, surroundings, `decay_distinguishable`; `searched_range_hz` | the search did not run or was narrowed (note, not "no resonance"); a candidate whose decay is not clearly longer than both the filter's ringing and its surroundings is not `decay_distinguishable` | `tests/unit/test_resonance.py` |
| Decay range and truncation | `peak_to_noise_db`, `noise_floor_db`, `truncation_time_s`, the Lundeby problem in the reason | see EDT / T20 / T30; a rejected iteration falls back to the preliminary estimate and the sensitivity check decides whether the metrics stay valid | `test_decay.py`, `test_acoustic_oracle.py` |
| Sample-rate mismatch | warning; the reference regenerated at the recording's rate; `PlaybackSpeed(kind="sample_rate")` when the file was played unconverted | a recording and a separate loopback at different rates are refused; a played-unconverted sweep marks every decay and energy metric unreliable with the speed in the reason; an imported band above Nyquist is refused | `tests/integration/test_playback_speed.py` (44.1 / 88.2 / 96 kHz unconverted), `tests/unit/test_sweep.py` |
| Playback speed / time stretch | `PlaybackSpeed(speed_ratio, kind="time_stretch")` | within the tolerance for the sweep length nothing is reported; beyond it every decay and energy metric is unreliable, and a recording cut inside the sweep is named as such, not as a stretch | `tests/integration/test_playback_speed.py` (±3 %), `tests/integration/test_recording_checks.py` |
| Loopback timing and compensation | `LoopbackResult`: `compensation_applied`, `reason`, path delay | a silent, clipped, low-confidence or room-like loopback is refused; a loopback found on another sweep pass than the microphone is refused; a loopback with device timing faults is refused; the microphone take is still evaluated uncompensated | `tests/unit/test_loopback.py` |
| Device clock, latency, buffer faults | `AudioSignal.device_warnings` → result warnings → every decay and energy metric unreliable; the `audio stream:` log line (devices, requested and reported rate, channels, block size, latency); `doctor` shows the driver's default latency | buffer under/overflow or a reported stream rate off by more than 0.5 Hz; a faulty separate loopback is not used | `tests/unit/test_portaudio_backend.py` (scripted stand-in), `tests/integration/test_recording_checks.py`, `tests/unit/test_diagnostics.py` |
| Invalid or non-finite input | refusal | NaN, Inf, a sample too large to square, a non-positive or non-integer sample rate, a two-dimensional array, a silent recording, a recording shorter than one second | `test_acoustic_oracle.py`, `tests/robustness/test_untrusted_files.py` |
| Placement geometry | `PlacementLength` with `validity`, `reason`, propagated uncertainty; the quantities ReverbScope refuses to infer are named in the result | a missing input or an inconsistent arrival gives `reason`, not a number; no coordinate, room length or wall distance is ever reported | `tests/unit/test_placement.py`, `tests/integration/test_placement_roundtrip.py` |
| Comparisons and project averages | each delta with a validity (`not_comparable` when either side is not valid or the sessions differ in band, reference or gating); averages carry the count behind every value | a refused comparison reports no findings; a negative baseline gives no percent change | `tests/unit/test_compare.py`, `tests/unit/test_averaging.py` |

## Result of the audit

No reported number was found without a carrier for its validity,
confidence or reason, and no gate was found that could be bypassed by an
input the code accepts. The candidate therefore freezes this behaviour; a
correctness defect found on real equipment is fixed on the candidate line
with a regression test first (`docs/RELEASE_PLAN.md` §2a).

## What only real equipment can settle

* The thresholds are engineering choices checked on synthetic signals:
  the 20 / 10 dB confidence bands, the 20 dB rival-arrival rule and its
  12 dB gap, B·T ≥ 4, the straightness constants, the 0.5 Hz rate
  tolerance, the playback-speed tolerance. Real rooms, real interfaces and
  real DAW exports may show that one of them withholds too much or too
  little; that is a candidate finding, not a synthetic one.
* The direct sound of a real microphone in a real room (close reflections,
  loudspeaker pre-ringing, interface latency) has only been simulated.
* The reported stream rate and latency are PortAudio's values; whether a
  given driver reports the truth is a hardware row in
  [HARDWARE_TESTS.md](HARDWARE_TESTS.md).
* Agreement with a reference instrument is the validation campaign in
  [VALIDATION.md](VALIDATION.md); nothing here replaces it.
