# Guided diagnostics (experimental)

This document describes the guided assistant on
`experimental/guided-acoustic-assistant`. It is **not** part of the 0.5 stable
or release-candidate feature set. The measurement core does not import it.

## Data flow

```text
Measurement pipeline
    -> deterministic diagnostic engine
    -> structured findings
    -> recommendation planner
    -> knowledge catalog
    -> explanation provider
    -> GUI / CLI
```

Professional facts come only from ReverbScope DSP, deterministic rules, and
validated metrics. A model is an untrusted explanation layer. It does not
compute acoustics, invent numbers, name a reflecting surface, or decide
whether take B is better than take A.

## What offline mode can do

With no network, no model, and no API key the assistant can still measure
(the existing core), diagnose, rank the next action, explain it from the
built-in catalog, and compare two takes.

## Languages

English and Simplified Chinese are complete. Traditional Chinese, Japanese,
Korean, Spanish, French, German, and Portuguese are accepted and currently
fall back to the English catalog, with a one-line notice in that language.

## Findings

`strong_early_reflection`, `low_frequency_decay_long`, `low_frequency_peak`,
`low_frequency_null`, `high_noise_floor`, `mains_hum_detected`,
`insufficient_decay_range`, `low_direct_sound_confidence`, `input_too_hot`,
`signal_too_low`, `clipping_detected`, `sample_rate_mismatch`,
`time_stretch_detected`, `device_timing_suspicious`, `audio_dropout_detected`.

Thresholds, with rationale and limitations, live in
`reverbscope.experimental.guided.thresholds`.

## Compare

The comparison engine reports Improved, Slightly improved, Worse, Slightly
worse, Unchanged, Mixed, or Not comparable for each item. There is no room
score.
