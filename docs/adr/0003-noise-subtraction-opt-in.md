# Keep experimental noise-power subtraction opt-in

This decision follows GUIDELINES.zh-CN.md §3 D11, §4 C12/C16 and §6.
Status: proposed for maintainer review, on a task branch based on PR #72.

## Problem

PR #72 enables Hirata-style noise-power subtraction by default. The Lundeby
estimate must have no problem flag and more than 40 dB of dynamic range,
but those conditions do not establish that its estimated floor is noise.

An independent, noiseless signal `exp(-ln(1000) * t / 0.8)` at 8 kHz,
followed by zeros once it falls 50 dB, reproduces the problem. The guarded
default subtracts remaining signal power, and the public band analysis
returns a valid T30 of approximately 0.7861 s instead of 0.8 s. With
subtraction disabled it returns approximately 0.8000 s. A 45 dB cutoff also
changes the fitted energy-decay slope, although the public T30 for that
shorter signal is correctly withheld by the existing decay-range rule.

## Decision

- Disable subtraction by default in both `schroeder_curve` and its internal
  curve builder. Existing band-analysis and truncation-sensitivity callers
  retain the unsubtracted integration policy.
- Keep the implementation available through explicit
  `schroeder_curve(..., subtract_noise=True)`. Preserve the finite-floor,
  no-problem and strictly-greater-than-40-dB guard unchanged.
- Restore the default method description so reported band results do not
  claim to use noise subtraction. Do not change validity thresholds, file
  formats, GUI controls, CLI output structure or dependencies.
- Keep the existing late-decay compensation. This decision does not choose
  a replacement floor estimator or claim that clipping corrected sample
  powers gives an unbiased noise estimator.

## Evidence and limits

`tests/unit/test_noise_subtraction_policy.py` checks known-answer noiseless
decays, the public T30 path, explicit opt-in, the 40 dB boundary, rejected
and non-finite floor estimates, finite monotonic energy curves and input
preservation. The 1% known-answer tolerance is a regression-test choice,
not an ISO accuracy or compliance limit.

Evidence is synthetic and automated. Noise subtraction remains experimental
even when explicitly requested; the guard cannot distinguish all valid
noise floors from residual signal. Real rooms, hardware and DAWs have not
been validated by these tests. Re-enabling this policy by default requires
separate evidence and maintainer review. No change is made to the duplicate
implementation in PR #74 or to its synchronization and modal estimators.
