# Report the uncertainty of the single/double-slope decay fit

This decision follows GUIDELINES.zh-CN.md §3 D11 (a core change gets its own
ADR), §4 C1/C2/C12/C16 and docs/API_STABILITY.md. It builds on ADR 0004.
Status: proposed for maintainer review on `feat/decay-uncertainty` (based on
`feat/double-slope-fit`). Numbered 0006 because a parallel branch proposes
an ADR 0005.

## Problem

The slope fit of ADR 0004 reports T1, T2, amplitudes, a noise term and a
turning point with no indication of how well the curve determines them. A
forced two-slope fit of a straight decay returns some T2 however meaningless
it is, and a 50 Hz one-third-octave T1 is far less certain than a 2 kHz
octave one, yet both are printed to two decimals.

## Decision

- Add `core/multislope.py:slope_uncertainty`, computed after each fit from
  its solution (the fit itself is untouched). It is the sum of two Gaussian
  covariances in the fit's log parameters (methodology §3d):
  1. the **analysis term** of Xiang & Sü Gül (J. Acoust. Soc. Am. 158,
     2892–2901, 2025): the Laplace approximation of their Student-t
     posterior with uniform priors, `(Q/K)(JᵀJ)⁻¹`, with the decay data
     counted at their adequate data rate `f_d = 110/T1`;
  2. a **stochastic-decay term**: the covariance of the Schroeder curve of
     band-limited Gaussian noise (`Var EDC(t) = (1/B)∫_t^L e²`, shared tail
     between points), propagated through the least-squares fit as a
     sandwich. This term is ReverbScope's derivation, not the paper's.
- Store it per model as `uncertainty` in `multi_slope.models[]` of
  `result.json` (additive, schema 1 unchanged; `null` when it cannot be
  computed; older files load with none). Standard deviations and 68 %/95 %
  intervals of `T_i` (log-normal), standard deviations of `A_i` and `N` in
  dB, of the turning point, the analysis term alone, `K_d`, `f_d` and
  whether the 100-point grid met `f_d`.
- Show it additively: 13 columns appended to `decay_slopes.csv` (existing
  columns unchanged), `± σ` in the report's two slope tables plus one
  explanatory paragraph, a sentence after the Decay view's fit note and a
  "Slope uncertainty" inspector row with a tooltip.
- Keep the 100-point fit grid. The paper's point that decimated decay data
  suffice is confirmed on Aachen (50–400 points change T by a median
  0.1–0.25 %, never the slope count); changing the grid would change every
  number of ADR 0004 for no measurable gain.

## Why not the analysis term alone

It is what the paper supports, but it describes how precisely one curve
fixes the parameters, not the random fluctuation of a reverberant decay. On
synthetic decays its 95 % interval covered the generating decay time in
only 13–36 % of fits; with the stochastic term, 97 % (68 % interval: 74 %).
The paper's own comparison is with repeated measurements of one position,
which share the room's fine structure; ReverbScope's calibration varies the
fine structure as well. The analysis term is still reported separately
(`decay_times_analysis_sd_s`) so a reader can see both.

## Why not bootstrap or nested sampling

A block bootstrap or the nested sampling the paper points to would need
tens to thousands of refits per band; the chosen terms reuse the fit's
Jacobian and cost about 0.5 ms per model (about 1 % of a position's octave
decay analysis on the Linux aarch64 test machine). numpy/scipy only, no new
dependency.

## Evidence and limits

`tests/unit/test_decay_uncertainty.py` (coverage on synthetic decays, single
and double, octave and one-third octave; the fit unchanged; round trip; old
files) and [validation/decay-uncertainty.md](../validation/decay-uncertainty.md)
(17-case calibration; Aachen St. Nicholas Chapel interval widths and the
DecayFitNet comparison). The uncertainty covers one response at one
position: not position-to-position spread, equipment or repeated set-ups,
nor the choice of the number of slopes. It assumes a diffuse decay. The
paper's equations are images on the publisher's page; the data-rate
constant is reconstructed from its text and examples. The Aachen run is
third-party measured data analysed offline; it is not a ReverbScope
hardware or DAW test (C16).
