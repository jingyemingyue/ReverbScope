# Validation: uncertainty of the slope fit

How far the uncertainty of the single/double-slope fit
(methodology §3d, [ADR 0006](../adr/0006-decay-fit-uncertainty.md)) can be
trusted: coverage of its intervals on synthetic decays with known decay
times, and what it says on the measured St. Nicholas Chapel responses
([aachen-nikolauskapelle.md](aachen-nikolauskapelle.md)). Linux aarch64,
this branch (ReverbScope 0.5.0b6 plus the slope fit, its one-third-octave
path and the uncertainty).

## Method in one paragraph

Each model's covariance is the sum of Xiang & Sü Gül's analysis term (the
Laplace approximation of their Student-t posterior, the decay data counted
at `f_d = 110/T1`; J. Acoust. Soc. Am. 158, 2892–2901, 2025,
doi:10.1121/10.0039556) and a stochastic-decay term (the covariance of the
Schroeder curve of band-limited Gaussian noise, through the least-squares
sandwich). Intervals of `T_i` are log-normal. Details in methodology §3d.

## Synthetic calibration

Responses: Gaussian noise under one or two exponential power envelopes plus
a stationary noise floor (`tests/unit/test_multislope.decay`), direct sound
at 0.2 s, 48 kHz, filtered with ReverbScope's time-reversed band filters and
analysed by `core.decay.analyze_band`; 150 seeds per case (seeds 1000–1149),
a fresh noise realisation each. "Coverage" is the share of fits whose
interval contains the generating decay time (for two-slope cases, the
two-slope model; the knee truth is `ln(A1/A2)/(13.8155·(1/T1 − 1/T2))` from
the generating amplitudes). "paper-only" is the 95 % coverage of the
analysis term alone. "±" is the median 95 % half-width relative to `T`.
"grid ≥ f_d": share of fits whose 100-point grid is at least as dense as
`110/T1`. "fit ms": the whole `analyze_band` call (ISO metrics included).

| T (s) | band | noise dB | n | coverage | grid≥f_d | fit ms |
|---|---|---|---|---|---|---|
| 0.3 | 1000 Hz oct | -75 | 150 | T1 c68 0.71 c95 0.97 (paper-only c95 0.27) ±3.3% | 0.00 | 21 |
| 0.5 | 1000 Hz oct | -75 | 150 | T1 c68 0.72 c95 0.97 (paper-only c95 0.30) ±2.5% | 0.00 | 62 |
| 1.5 | 1000 Hz oct | -75 | 150 | T1 c68 0.73 c95 0.95 (paper-only c95 0.36) ±1.4% | 0.00 | 114 |
| 3.0 | 1000 Hz oct | -75 | 150 | T1 c68 0.77 c95 0.98 (paper-only c95 0.33) ±1.0% | 0.00 | 140 |
| 1.0 | 125 Hz oct | -75 | 150 | T1 c68 0.77 c95 0.96 (paper-only c95 0.34) ±4.9% | 0.00 | 91 |
| 2.5 | 4000 Hz oct | -75 | 150 | T1 c68 0.78 c95 0.95 (paper-only c95 0.35) ±0.6% | 0.00 | 116 |
| 1.0 | 1000 Hz oct | -55 | 150 | T1 c68 0.72 c95 0.99 (paper-only c95 0.35) ±3.1% | 0.00 | 81 |
| 1.0 | broadband | -75 | 150 | T1 c68 0.68 c95 0.97 (paper-only c95 0.28) ±0.3% | 0.00 | 107 |
| 1.0 | 1000 Hz 1/3 | -75 | 150 | T1 c68 0.73 c95 0.97 (paper-only c95 0.31) ±3.1% | 0.00 | 63 |
| 0.8 | 250 Hz 1/3 | -75 | 150 | T1 c68 0.77 c95 0.96 (paper-only c95 0.27) ±6.8% | 0.00 | 83 |
| 2.0 | 4000 Hz 1/3 | -60 | 150 | T1 c68 0.72 c95 0.97 (paper-only c95 0.29) ±1.6% | 0.00 | 209 |
| 0.4/1.6 (-25 dB) | 1000 Hz oct | -75 | 150 | T1 c68 0.77 c95 0.97 (paper-only c95 0.14) ±11.0% ; T2 c68 0.73 c95 0.97 (paper-only c95 0.15) ±3.5% ; knee c68 0.76 c95 0.95 | 0.00 | 87 |
| 1.0/3.0 (-25 dB) | 1000 Hz oct | -75 | 150 | T1 c68 0.65 c95 0.97 (paper-only c95 0.15) ±5.9% ; T2 c68 0.78 c95 0.99 (paper-only c95 0.19) ±3.3% ; knee c68 0.65 c95 0.96 | 0.00 | 131 |
| 0.6/2.0 (-20 dB) | 2000 Hz oct | -75 | 150 | T1 c68 0.77 c95 0.96 (paper-only c95 0.17) ±8.3% ; T2 c68 0.71 c95 0.95 (paper-only c95 0.21) ±1.9% ; knee c68 0.75 c95 0.97 | 0.00 | 72 |
| 1.0/3.0 (-25 dB) | 250 Hz oct | -75 | 150 | T1 c68 0.71 c95 0.97 (paper-only c95 0.15) ±11.7% ; T2 c68 0.74 c95 0.96 (paper-only c95 0.25) ±6.5% ; knee c68 0.73 c95 0.95 | 0.00 | 144 |
| 1.0/3.0 (-25 dB) | 500 Hz 1/3 | -75 | 150 | T1 c68 0.75 c95 0.97 (paper-only c95 0.19) ±14.4% ; T2 c68 0.70 c95 0.98 (paper-only c95 0.19) ±8.1% ; knee c68 0.75 c95 0.97 | 0.00 | 135 |
| 0.5/2.0 (-20 dB) | 2000 Hz 1/3 | -75 | 150 | T1 c68 0.80 c95 0.96 (paper-only c95 0.29) ±17.6% ; T2 c68 0.78 c95 0.98 (paper-only c95 0.13) ±3.1% ; knee c68 0.81 c95 0.97 | 0.00 | 152 |

Pooled over cases: single slope 1 650 decay times, coverage 73.6 % (68 %
interval) and 96.7 % (95 % interval); double slope 1 800 decay times,
74.1 % and 96.8 %. The intervals are slightly conservative (wider than
nominal); the analysis term alone would cover 13–36 %.

The unit tests (`tests/unit/test_decay_uncertainty.py`, 5 cases × 30 seeds)
hold the 68 % coverage in [0.58, 0.88] and the 95 % coverage in
[0.89, 1.00]; when written they gave 81 % / 99 % (single, 90 decay times)
and 73 % / 97 % (double, 120).

## St. Nicholas Chapel (Aachen), 46 positions

Same run as [aachen-nikolauskapelle.md](aachen-nikolauskapelle.md)
(`scripts/validate_aachen_nikolauskapelle.py --uncertainty-summary`);
per-band summary in
[`aachen-nikolauskapelle-uncertainty.csv`](aachen-nikolauskapelle-uncertainty.csv)
(derived from Zerwas & Kayku, doi:10.5281/zenodo.20428705, CC-BY 4.0).
VALID fits only. "selected T": the decay time(s) of the model the criterion
chose; "2-slope T1/T2": the two-slope model, also when it was not chosen
(DecayFitNet always gives two slopes). Half-widths are of the 95 % interval,
relative to the value, median [IQR] over positions. "DFN in RS 95 %":
DecayFitNet's octave T1 (T2) inside ReverbScope's two-slope 95 % interval
(for the thirds: the octave value of the octave the third lies in — not like
for like). "no uncertainty": selected models with a parameter at a bound or
a singular fit.

| Resolution | Band | n | selected T: 95 % half-width median [IQR] | 2-slope T1 half-width | 2-slope T2 half-width | analysis term / total (T1) | DFN T1 in RS T1 95 % | DFN T2 in RS T2 95 % | same, RS chose 2 slopes (T1; T2) | no uncertainty (selected model) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| octave | 63 Hz | 46 | 6.8 % [5.2, 8.7] | 40.5 % [18.8, 83.7] | 40.8 % [12.1, 129.0] | 0.16 | 30/33 | 28/33 | 4/4; 4/4 | 0 |
| octave | 125 Hz | 46 | 4.3 % [3.4, 5.3] | 55.5 % [24.9, 248.1] | 41.2 % [12.5, 119.0] | 0.21 | 20/23 | 19/23 | 2/2; 2/2 | 0 |
| octave | 250 Hz | 46 | 3.0 % [2.7, 3.8] | 11.7 % [5.2, 75.4] | 147.6 % [8.6, 345.8] | 0.19 | 15/25 | 17/25 | 1/1; 1/1 | 0 |
| octave | 500 Hz | 46 | 2.2 % [1.7, 3.3] | 121.9 % [4.7, 442.3] | 3.5 % [2.7, 9.6] | 0.22 | 16/19 | 2/19 | 2/4; 0/4 | 0 |
| octave | 1000 Hz | 46 | 1.5 % [1.1, 2.8] | 4.6 % [2.6, 41.8] | 23.8 % [7.8, 60.0] | 0.31 | – | – | –; – | 0 |
| octave | 2000 Hz | 46 | 1.3 % [1.0, 2.7] | 8.3 % [2.3, 37.0] | 5.0 % [2.2, 15.2] | 0.39 | – | – | –; – | 0 |
| octave | 4000 Hz | 46 | 1.3 % [1.0, 3.8] | 10.1 % [6.6, 18.2] | 3.0 % [2.2, 5.3] | 0.56 | – | – | –; – | 0 |
| octave | 8000 Hz | 46 | 2.3 % [1.4, 3.7] | 3.1 % [2.1, 4.6] | 4.3 % [3.8, 6.2] | 0.49 | – | – | –; – | 0 |
| third | 50 Hz | 46 | 19.3 % [13.6, 32.0] | 58.5 % [35.4, 105.9] | 31.1 % [19.8, 83.2] | 0.11 | 21/27 | 20/27 | 8/11; 9/11 | 0 |
| third | 63 Hz | 46 | 14.1 % [9.8, 16.7] | 50.8 % [21.8, 171.7] | 105.9 % [26.7, 502.7] | 0.14 | 26/27 | 20/27 | 5/6; 5/6 | 0 |
| third | 80 Hz | 46 | 9.2 % [7.0, 11.0] | 50.5 % [25.4, 176.4] | 88.8 % [15.5, 575.0] | 0.15 | 29/33 | 28/33 | 2/2; 2/2 | 0 |
| third | 100 Hz | 46 | 7.7 % [6.3, 9.4] | 58.4 % [13.9, 277.6] | 136.8 % [47.5, 322.0] | 0.15 | 25/27 | 22/27 | 1/1; 1/1 | 0 |
| third | 125 Hz | 46 | 7.1 % [5.8, 8.9] | 80.4 % [26.6, 704.1] | 47.5 % [19.9, 104.3] | 0.19 | 19/21 | 15/21 | 2/3; 2/3 | 0 |
| third | 160 Hz | 45 | 6.5 % [5.5, 7.8] | 57.8 % [13.6, 141.9] | 50.7 % [13.0, 173.4] | 0.16 | 21/25 | 20/25 | –; – | 0 |
| third | 200 Hz | 46 | 6.2 % [5.2, 7.2] | 15.6 % [10.1, 530.1] | 40.5 % [12.6, 194.5] | 0.19 | 15/19 | 12/19 | 1/1; 0/1 | 0 |
| third | 250 Hz | 46 | 5.3 % [4.8, 6.5] | 28.6 % [10.3, 405.7] | 55.5 % [9.0, 241.4] | 0.18 | 18/22 | 16/22 | –; – | 1 |
| third | 315 Hz | 46 | 4.4 % [4.0, 6.2] | 44.5 % [9.2, 331.5] | 16.4 % [9.3, 64.8] | 0.22 | 17/20 | 9/20 | 2/2; 1/2 | 1 |
| third | 400 Hz | 46 | 4.0 % [3.4, 5.7] | 47.1 % [10.4, 309.2] | 33.8 % [6.6, 172.1] | 0.20 | 24/26 | 16/26 | 2/2; 0/2 | 0 |
| third | 500 Hz | 46 | 3.7 % [2.9, 5.4] | 48.6 % [5.3, 538.6] | 15.4 % [9.8, 86.9] | 0.19 | 17/20 | 10/20 | 2/3; 1/3 | 0 |
| third | 630 Hz | 46 | 3.2 % [2.6, 5.0] | 7.2 % [5.1, 317.2] | 9.9 % [4.5, 49.9] | 0.19 | 12/16 | 6/16 | 2/4; 0/4 | 0 |
| third | 800 Hz | 46 | 2.7 % [2.1, 4.4] | 11.4 % [4.9, 157.0] | 12.0 % [6.0, 44.2] | 0.25 | – | – | –; – | 0 |
| third | 1000 Hz | 46 | 2.5 % [2.0, 3.9] | 7.5 % [3.2, 150.7] | 23.5 % [7.4, 51.1] | 0.29 | – | – | –; – | 0 |
| third | 1250 Hz | 46 | 2.1 % [1.7, 2.9] | 3.9 % [2.7, 8.6] | 30.4 % [15.9, 51.2] | 0.28 | – | – | –; – | 0 |
| third | 1600 Hz | 46 | 2.0 % [1.4, 2.8] | 6.9 % [2.6, 68.9] | 10.3 % [4.9, 25.4] | 0.32 | – | – | –; – | 0 |
| third | 2000 Hz | 46 | 2.0 % [1.4, 2.7] | 6.7 % [2.8, 96.0] | 7.2 % [2.6, 23.5] | 0.35 | – | – | –; – | 0 |
| third | 2500 Hz | 46 | 1.8 % [1.3, 2.4] | 55.9 % [3.5, 108.6] | 5.5 % [2.3, 14.8] | 0.38 | – | – | –; – | 0 |
| third | 3150 Hz | 46 | 1.6 % [1.3, 2.2] | 62.8 % [3.7, 136.7] | 3.9 % [2.2, 19.9] | 0.40 | – | – | –; – | 0 |
| third | 4000 Hz | 46 | 1.7 % [1.3, 2.0] | 40.5 % [2.8, 85.5] | 4.7 % [2.4, 22.0] | 0.37 | – | – | –; – | 1 |
| third | 5000 Hz | 46 | 1.7 % [1.4, 2.2] | 36.9 % [2.5, 72.5] | 6.2 % [3.7, 18.9] | 0.50 | – | – | –; – | 0 |
| third | 6300 Hz | 46 | 1.4 % [1.2, 1.9] | 32.1 % [2.5, 64.4] | 4.7 % [2.3, 30.1] | 0.34 | – | – | –; – | 1 |
| third | 8000 Hz | 46 | 1.5 % [1.3, 2.1] | 18.6 % [7.3, 41.5] | 9.6 % [4.7, 17.7] | 0.24 | – | – | –; – | 0 |
| third | 10000 Hz | 46 | 1.8 % [1.6, 2.4] | 12.5 % [6.2, 23.0] | 17.4 % [7.8, 33.2] | 0.12 | – | – | –; – | 0 |

Findings:

* **Widths follow the band's bandwidth and decay time.** For the selected
  model the median 95 % half-width is 1.3–6.8 % in octave bands (widest at
  63 Hz) and 1.4–19 % in one-third-octave bands (19 % at 50 Hz, 14 % at
  63 Hz, at most 4 % from 400 Hz up), as expected of a random decay whose
  relative spread grows as `1/√(B·T)`.
* **A forced two-slope model of a straight decay is visibly not identified.**
  Where one slope was chosen, the two-slope T1 and T2 intervals are often
  wider than the values themselves (median half-widths up to about 150 %); the forced
  numbers in `decay_slopes.csv` are now flagged by their own intervals.
* **The stochastic term dominates.** The analysis term is 11–56 % of the
  total standard deviation of T1 (median per band), smallest at low
  frequencies.
* **DecayFitNet's T1/T2 against ReverbScope's intervals.** Where ReverbScope
  chose two slopes, DecayFitNet's T1 and T2 lie inside its 95 % intervals at
  63 Hz (4/4, 4/4), 125 Hz (2/2, 2/2) and 250 Hz (1/1, 1/1), but not at
  500 Hz (T1 2/4, T2 0/4): there ReverbScope's T2 interval is narrow
  (median half-width 3.5 %) and DecayFitNet's slopes are the least distinct
  (median T2/T1 1.16, aachen-nikolauskapelle.md), so the two analyses
  describe different late slopes. Against the forced two-slope models,
  DecayFitNet's T1 is inside in 84–91 % of positions at 63, 125 and 500 Hz
  and 60 % at 250 Hz; its T2 in 68–85 % at 63–250 Hz and 11 % at 500 Hz.
  DecayFitNet is another estimator, not a reference value: inclusion is a
  consistency check, not a coverage test.
* **Missing intervals.** Every one-slope model and every selected octave
  model has an uncertainty; 4 of 1 103 selected one-third-octave models have
  none. Of all two-slope models (mostly forced, not selected), 119 of 368
  octave and 452 of 1 103 one-third-octave ones have none: a decay time or
  amplitude at its bound (for example T2 at its 4·L limit, seen when
  inspecting S1-R21 at 500 Hz) or a singular fit; the reasons were not
  tallied. Such fits are degenerate, and no interval is better than a
  misleading one.

## Fit grid and speed

* The 100-point fit grid was coarser than the paper's `110/T1` in every
  Aachen band and synthetic case (`grid_adequate` false; `K_d` 120–930
  points at four positions). Refitting four positions (S1-R1, S2-R5,
  S3-R9, S1-R21; 32 octave bands) on 50, 200 and 400 points changed the
  one-slope T by a median of 0.25 %, 0.12 % and 0.15 % (at most 3.4 %),
  never changed the slope count, and changed the reported standard
  deviation by less than 1 % (median ratio 0.99 between 100 and 400 points).
  The grid is kept (ADR 0006).
* The uncertainty costs about 0.5 ms per model (108 calls over three
  positions); the octave decay analysis of a position took 1.02 s with it
  and 1.04 s without it (median of six runs; the difference is within the
  run-to-run noise of a shared machine).
* Every number of the existing outputs is unchanged: the octave CSV of
  aachen-nikolauskapelle.md (4 784 cells compared) and the thirds summary
  CSV are identical with the uncertainty added.

## Limits

* The calibration uses the model the uncertainty assumes (diffuse,
  Gaussian-noise decays with exact exponential envelopes). Real rooms have
  discrete reflections, modes and non-exponential decays; the Aachen run
  shows widths and consistency, not coverage, because the true decay times
  are unknown.
* The uncertainty is for one response at one position; position-to-position
  spread (here: 46 positions) is larger and is not included.
* The paper's equations are images on the publisher's page; the data-rate
  constant (≈ 110/T) is ReverbScope's reconstruction, consistent with the
  paper's 50 Hz at 2.18 s and 10 Hz at 11.5 s.
* Synthetic cases stop at 125 Hz octave / 250 Hz third; the Aachen 50–100 Hz
  thirds have intervals but no coverage check.
