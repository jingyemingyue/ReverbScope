# Measurement Health

[简体中文](MEASUREMENT_HEALTH.zh-CN.md)

Measurement Health appears near the start of analysis text reports and at
the top of the Results overview. Every issue has a stable code, severity,
short title, explanation, evidence and next step. It helps fix a measurement;
it does not grade a room or certify a device or DAW.

| Status | Meaning |
| --- | --- |
| GOOD | The available measurement checks found no problem. |
| WARNING | There is a limitation, rejected optional reference or affected metric to address. |
| INVALID | A clipping, direct-sound, playback-speed or microphone-device timing diagnosis prevents reliable decay/energy conclusions from this take. |
| UNKNOWN | A check or its evidence is absent or unrecognised. This is not a pass. |

Aggregate precedence is **INVALID > WARNING > UNKNOWN > GOOD**. Missing
optional loopback is normal. A supplied but rejected loopback is a warning;
timing faults in that unused electrical reference alone do not invalidate
the uncompensated microphone recording. Device timing faults in the actual
take are INVALID even with high direct-sound confidence.

## Evidence and actions

| Stable code | Evidence and action |
| --- | --- |
| `recording.clipping` | Existing flat-top/clipping diagnostic, including attenuated exports. Lower preamp gain or playback level, remove nonlinear processing and remeasure. |
| `direct_sound.medium_confidence` | Existing medium confidence and pre-peak margin. Verify placement and the reference. |
| `direct_sound.low_confidence` | Existing low confidence. EDT/T20/T30/C50/C80/D50 and reflection timing may be unreliable; improve the direct path/SNR and remeasure. |
| `decay.insufficient_range` | Existing `insufficient_decay_range` validity, affected metrics and reasons. This is not RT60 = 0; lower noise, improve placement and adjust playback within available headroom. |
| `playback.sample_rate_mismatch` | Existing playback-speed diagnosis. Check project rate, import conversion, interface rate and playback conversion. |
| `playback.time_stretch` | Existing time-stretch diagnosis. Disable Warp, Flex, Follow Tempo, Musical Mode and clip stretching. |
| `device.timing` | Existing buffer/underflow/overflow, reported rate or timing-fault diagnostics. Increase buffer/latency, check rates and clock, close competing audio programs and remeasure. |
| `noise.limited_range` | Existing insufficient-range flags with finite peak-to-noise evidence. Noise, duration or placement can limit the usable range; improve the capture. |
| `reflection.truncated_window` | Existing truncated-window flag and requested/available windows. Record a longer tail, separate sweep passes and preserve the complete response. |
| `loopback.rejected` | Existing rejected electrical reference. Check routing, level and clock; correct it or explicitly use an uncompensated measurement. |
| `analysis.warning` | Unrecognised analyzer warnings remain visible with their original evidence. |

Other codes explain a short recorded tail, unreliable/uncomputed metrics,
unexcited or unknown bands, and missing clipping/noise/confidence/result
evidence. An unrecognised playback diagnosis uses
`playback.unknown_diagnosis`; it never becomes an invented time-stretch claim.

## Engineering boundaries

`reverbscope.measurement_health.derive_measurement_health(result)` returns
an immutable, ephemeral view in the active language. It reads the existing
`AnalysisResult`, without running DSP or changing a metric's validity.
Finding codes and severities are independent of language. CLI symbols and
GUI colours always have text equivalents; unknown evidence is neutral,
warnings amber and invalid measurements red.

There is no 0–100 score and no new numeric acceptance threshold. Range
findings use the core's existing validity gate: `core.decay._fit_metric`
requires the evaluation range plus its configured noise margin and enough
curve samples. Health does not refit or repeat that decision. It does not
infer acoustic noise quality from an uncalibrated dBFS level. Missing noise
or peak-to-noise data stays UNKNOWN rather than being treated as zero.

Schema v1 device diagnostics are English sentences, so their existing
producer forms are recognised centrally, before translation. Incidental
keywords such as “no overflow” are not diagnosed as a device fault.
Unrecognised warnings remain WARNING with their evidence.

The CLI `--format json`/`--json` payload and result/session/project schemas
are unchanged. No health fields are persisted. Python callers may explicitly
derive the view; there is no new machine-readable CLI output in this batch.
No runtime dependency is added. Synthetic and offscreen tests are not
real hardware or DAW validation.
