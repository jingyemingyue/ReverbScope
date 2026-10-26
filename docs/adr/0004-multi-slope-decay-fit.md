# Fit single and double slopes to the energy decay

This decision follows GUIDELINES.zh-CN.md §3 D11 (a core change gets its own
ADR), §4 C1/C2/C12/C16 and docs/API_STABILITY.md.
Status: proposed for maintainer review on `feat/double-slope-fit`.

## Problem

`core/decay.py` flags a non-straight decay (ISO 3382-2 Annex B curvature and
non-linearity) and then withholds T20/T30 as unreliable, with the sentence
"possibly a double slope, coupled volumes or strong early reflections". It
never says which. Users with coupled rooms get no number at all.

## Decision

- Add `core/multislope.py`: a classical, dependency-light (NumPy/SciPy) fit
  of `EDC(t) = Σ A_i (exp(−13.8155 t/T_i) − exp(−13.8155 L/T_i)) + N (L − t)`
  with one and two slopes, chosen by BIC with an effective number of points
  and plausibility rules (methodology §3c). No PyTorch, no DecayFitNet
  weights, no new dependency.
- Store it per band as `multi_slope` in `result.json`: an additive key under
  schema 1 (API_STABILITY principle 1). Older files load with no fit; no
  number is invented for them.
- Leave every existing number unchanged: onset, truncation, EDT/T20/T30,
  RT60, C/ξ, the energy parameters and their validity. The existing
  straightness warning stays as it is; the fit sits beside it.
- Show it additively: a CSV file of its own (existing CSV files keep their
  columns), a report table only when a band has two slopes (the reports of
  single-slope rooms are unchanged, so the CLI goldens are unchanged), the
  Decay view overlay and one inspector row.

- Offer the fit in one-third-octave bands as an **opt-in analysis
  setting**, `AnalysisSettings.third_octave_decay` (`--third-octave`, a
  check box on the desktop measurement pages), off by default. ReverbScope
  had no user-facing band resolution setting and its decay analysis was
  octave-only, so a new default would have changed every report and tripled
  the decay work (0.44 s → 1.33 s for a 10 s, 48 kHz response) for a view
  most rooms do not need. The thirds (IEC 61260-1, base 10, the three inside
  each analysed octave) are analysed by the same `analyze_band` with their
  own bandwidth, on a separate segment with the lead-in of the narrowest
  third, so the octave results are bit-identical with the option on or off.
  They are stored as `decay.third_octave_bands` (additive, written only when
  asked for, schema 1), with a `resolution` column in `decay_slopes.csv`,
  a report table and a Resolution list in the Decay view.
- Keep the octave thresholds for one-third-octave bands. A synthetic
  re-check down to 50 Hz (methodology §3c) found the false-split rate of the
  50–100 Hz thirds equal to that of the 63 Hz octave the thresholds were
  accepted with, and fewer double slopes found only through `ΔBIC`; the
  bandwidth-dependent rules (`B·T1 ≥ 4`, onset window, lead-in) already use
  each band's own bandwidth. No per-band adjustment is made.

## Evidence and limits

Synthetic tests (`tests/unit/test_multislope.py`) and a run on the open
Aachen St. Nicholas Chapel data set
([validation/aachen-nikolauskapelle.md](../validation/aachen-nikolauskapelle.md)).
The thresholds are ReverbScope's choice; they are not from a standard.
DecayFitNet's published results are octave bands, so the one-third-octave
fit has no like-for-like reference in that data set; it is compared with the
octave each third lies in.
The data set run is third-party measured data analysed offline; it is not a
ReverbScope hardware or DAW test (C16).
