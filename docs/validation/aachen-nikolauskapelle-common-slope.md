# Validation on measured data: common slopes, St. Nicholas Chapel, Aachen

The common-slope analysis (methodology §3d,
[ADR 0005](../adr/0005-common-slope-analysis.md)) run on the 46 measured
responses of the coupled St. Nicholas Chapel, compared with ReverbScope's
per-response single/double-slope fits (§3c) and the authors' DecayFitNet
analysis. Data, licence and the per-response comparison are described in
[aachen-nikolauskapelle.md](aachen-nikolauskapelle.md).

This is third-party measured data analysed offline. It is not a ReverbScope
hardware, interface or DAW test; the responses are imported as impulse
responses. There is no ground truth for the decay times of a real room: the
comparisons below show agreement or disagreement between methods, not which
one is right.

## How it was run

```bash
python scripts/validate_common_slope_aachen.py --data ~/aachen \
    --out docs/validation/aachen-nikolauskapelle-common-slope.csv
```

All 46 W-channel responses (three sources: S1 with 22 receivers, S2 and S3
with 12) form one set, octave bands 63 Hz–8 kHz, direct sound at the
strongest sample, declared excitation 20 Hz–20 kHz (as in the per-response
validation). Each band is fitted with the default EDC estimator (LINEX
amplitudes) and with `--estimator is-sage`. The derived per-band table is
[`aachen-nikolauskapelle-common-slope.csv`](aachen-nikolauskapelle-common-slope.csv)
(same licence and attribution as the data, CC-BY 4.0); the raw data are not
in the repository. Run on 2026-10-25, branch `feat/common-slope`, aarch64
Linux sandbox shared with other jobs.

## Common decay times

| Band | per-response fits: 1 / 2 slopes | median T, one-slope fits (s) | DecayFitNet median T1 / T2 (s) | DecayFitNet T, k-means of all positions (s) | **common T, EDC (s)** | K | ΔBIC (1→2, 2→3) | positions supporting each slope | common T, IS-SAGE (s) | RMS error, median, common / per-response (dB) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 63 Hz | 42 / 4 | 4.14 | 3.37 / 5.02 | 3.35 / 5.24 | **4.19** | 1 | 164 / −212 | 46 | 4.04 | 1.22 / 0.53 |
| 125 Hz | 44 / 2 | 4.56 | 4.12 / 5.31 | 4.28 / 5.91 | **4.56** | 1 | −99 / −208 | 46 | 4.50 | 0.71 / 0.41 |
| 250 Hz | 45 / 1 | 4.77 | 4.33 / 5.63 | 4.38 / 6.03 | **4.82** | 1 | 67 / −161 | 46 | 4.78 | 0.49 / 0.33 |
| 500 Hz | 42 / 4 | 4.75 | 4.44 / 5.23 | 4.64 / 7.99 | **4.76** | 1 | −44 / −200 | 46 | 4.73 | 0.50 / 0.27 |
| 1 kHz | 42 / 4 | 4.44 | – | – | **4.46** | 1 | 19 / −233 | 46 | 4.44 | 0.74 / 0.34 |
| 2 kHz | 39 / 7 | 3.75 | – | – | **3.83** | 1 | 52 / −138 | 46 | 3.80 | 0.71 / 0.38 |
| 4 kHz | 36 / 10 | 2.62 | – | – | **2.68** | 1 | −73 / 106 | 46 | 2.65 | 0.81 / 0.49 |
| 8 kHz | 24 / 22 | 1.33 | – | – | **1.11 / 1.94** | 2 | 1173 / 7 | 46 / 20 | 1.16 / 2.21 | 0.45 / 0.43 |

DecayFitNet results are published for 63–500 Hz only and always have two
slopes; its "k-means" column clusters all 92 of its T1/T2 values per band
into two, the procedure of Götz et al. (2023), with ReverbScope's
`kmeans_log`.

**Findings.**

* **One common slope from 63 Hz to 4 kHz, two at 8 kHz.** This matches the
  per-response fits: they chose one slope at 85–98 % of the positions from
  63 Hz to 2 kHz and two at 22 of 46 positions at 8 kHz. The common single
  decay time lies within 2.1 % of the median of the per-response one-slope
  times (63 Hz–2 kHz; +2.5 % at 4 kHz), and between DecayFitNet's T1 and T2.
* **8 kHz:** 1.11 s and 1.94 s; every position supports the fast slope, 20
  support the slow one (the rule needs 3). The per-response two-slope fits
  give medians of 1.11 s and 2.01 s.
* **Rejected second slopes are artefacts the rules were made for.** At 250 Hz,
  1 kHz and 2 kHz the BIC favoured a second slope (ΔBIC 19–67), but its decay
  time was 9.5–17.7 s, 2–4 times the room's, and it was the strongest term
  over 10 dB at only one or two of 46 positions: late noise that rises or
  drifts in a few takes. At 63 Hz the forced two-slope common model gives
  **3.50 / 5.06 s, close to DecayFitNet (3.37 / 5.02 s median; 3.35 / 5.24 s
  k-means)**, but it halves the RMS error at no position (best 49.8 %, the
  rule needs 50 %), so one slope is reported. Forced two-slope models at
  125 Hz–4 kHz instead attach a weak 9.5–28 s tail (see the CSV): unlike
  DecayFitNet, ReverbScope does not find a second slope near 5–6 s there.
* **Cost of a shared decay time.** The median RMS difference between a
  position's EDC and the common model is 0.45–1.22 dB, against 0.27–0.53 dB
  for each response's own fit (which has its own T). The largest gap is at
  63 Hz (1.22 vs 0.53 dB), where the decay of a position depends most on
  its modes.
* **Sources.** Fitted per source (S1 22, S2 12, S3 12 positions), the
  single common slope agrees within about 5 % between sources from 125 Hz to 1 kHz
  (e.g. 500 Hz: 4.78 / 4.75 s for S2 / S3; S1 4.63 s). With only 12–22
  positions the support rule needs just 2: S1 then reports a weak 30 s tail at
  500 Hz and 1 kHz, S3 a 7.7 s one at 2 kHz, S1 two slopes at 63 Hz
  (3.50 / 5.16 s, as above) and 8 kHz (0.98 / 1.66 s), where S2 and S3 give
  one (1.38 / 1.52 s). The slow tails are the same artefact as above; a
  small set of positions does not rule it out.
* **IS-NMF / SAGE.** With one slope it agrees with the EDC estimate within
  3.6 % (63 Hz) and within 1.3 % from 125 Hz to 4 kHz. At 8 kHz it moves the
  pair to 1.16 / 2.21 s. It starts from the EDC estimate with the EDC's
  number of slopes; on its own the paper's method prescribes that number.

## Run time

Octave bands, 46 responses of 10 s at 48 kHz, Python 3.12, aarch64 sandbox
(shared with other jobs, so the times varied by 2× between runs):
observing the responses (band filtering, per-response fit, envelopes)
40–82 s, about 0.9–1.8 s per response; the common EDC fit 0.7–3.4 s per
band (K = 1–3 together); the IS-SAGE estimator 1–17 s per band. A project
of a few positions takes a few seconds. The analysis runs only when asked
for (command or button), never with a project load.

## Limits

* No ground truth: agreement with the per-response fits and partial
  agreement with DecayFitNet at 63 Hz is not proof of accuracy.
* The support (≥ 2 positions and ≥ 5 %) and improvement (≥ 50 % at one
  position) rules are ReverbScope's thresholds, set on synthetic rooms and
  checked here; with few positions a slow artefact can still pass (see
  Sources). Whether a cap on slow decay times relative to the record length
  should be added is left to the maintainer.
* The LINEX amplitude and IS-SAGE estimators are validated on synthetic
  data only (here and in their papers); the amplitudes of this run are in
  the per-position CSV written with `--positions`, not in the repository.
* One-third-octave bands (`--third-octave`) were not run on this data set.
