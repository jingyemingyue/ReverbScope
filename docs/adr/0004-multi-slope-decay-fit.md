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

## Evidence and limits

Synthetic tests (`tests/unit/test_multislope.py`) and a run on the open
Aachen St. Nicholas Chapel data set
([validation/aachen-nikolauskapelle.md](../validation/aachen-nikolauskapelle.md)).
The thresholds are ReverbScope's choice; they are not from a standard.
The data set run is third-party measured data analysed offline; it is not a
ReverbScope hardware or DAW test (C16).
