# Optional acoustic metrics: calibration, coverage and limits

This decision follows GUIDELINES.zh-CN.md §3 D11, §4 C1/C2/C12 and §6.
It applies to PR #75, independently of the GUI redesign. Status: draft,
for maintainer review.

## Decision

- G uses energy integrals, including the sample interval. A reference at
  distance d is converted to 10 m by multiplying its energy by `(d/10)^2`;
  the correction belongs in the denominator. The optional `sample_rate`
  argument states the measurement rate; omitting it assumes the reference
  rate. Non-positive energies withhold G. Negative/non-finite powers or
  invalid distances are errors. Log-energy sums avoid overflow.
- The reverberation-only STI estimate requires all seven octave bands.
  Missing bands do not get renormalized into a complete STI, and entirely
  silent data withholds the estimate. Use the published alpha weighting
  and adjacent-band beta redundancy formula. Power is normalized before
  the MTF calculation to preserve finite answers at extreme gains.
- This STI API does not apply ambient-noise, reception-threshold or
  level-dependent auditory-masking corrections. It is experimental and
  must not be presented as a validated IEC-compliant measurement.
- IACC uses the energy-normalized cross-correlation of the original
  responses, without Pearson mean subtraction. Independently normalize
  channel gains before arithmetic. Search only delays within ±1 ms, and
  keep a short response entirely within the 0–80 ms early window rather
  than inventing a late segment.

## Evidence and limits

`tests/unit/test_acoustic_metrics.py` checks free-field distance scaling,
different sample intervals, geometric-series analytic MTF values and the
redundancy formula, missing/silent/negative input, delay-window boundaries,
short responses, and gain invariance. All evidence is synthetic and
automated. No calibrated loudspeaker, binaural head, audio interface, real
room or IEC reference recording was tested.

No metric is wired into the GUI, a saved format, or existing CLI output by
this change. Integrating these experimental APIs requires a separately
reviewed presentation and validity contract.

## Sources

- Existing project conventions:
  [MEASUREMENT_METHODOLOGY.md](../MEASUREMENT_METHODOLOGY.md).
- MathWorks' [IEC 60268-16 verification example](https://www.mathworks.com/help/audio/ug/speech-transmission-index-iec60268-16-edition-5-compliance.html)
  publishes the alpha/beta coefficients and redundancy equation. Only
  mathematical constants and equations were used; no implementation copied.
- ISO 3382-1:2009 is the conceptual reference for G and IACC. The full
  standard was not available for clause-by-clause verification; this work
  makes no conformance claim.
