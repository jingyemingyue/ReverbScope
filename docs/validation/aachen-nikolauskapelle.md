# Validation on measured data: St. Nicholas Chapel, Aachen Cathedral

ReverbScope's decay analysis compared with published results for 46 measured
room impulse responses of an acoustically coupled chapel: EDT, T20 and T30
against the authors' ISO 3382-1 parameters, and the single/double-slope fit
(methodology §3c, [ADR 0004](../adr/0004-multi-slope-decay-fit.md)), in
octave and one-third-octave bands, against their DecayFitNet analysis.

This is third-party measured data analysed offline. It is not a ReverbScope
hardware, interface or DAW test, and it does not test sweep playback,
recording or deconvolution: the responses are imported as impulse responses.

## Data and attribution

M. Zerwas and S. Kayku, *Room acoustic measurement and decay analysis data of
the St. Nicholas Chapel, Aachen Cathedral*, Zenodo,
[doi:10.5281/zenodo.20428705](https://doi.org/10.5281/zenodo.20428705),
licensed [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/). The data
set accompanies M. Zerwas and S. Kayku, *Acta Acustica* (forthcoming), which
extends their DAGA 2026 report
([doi:10.71568/DAGA2026.137](https://doi.org/10.71568/DAGA2026.137)).

The chapel is a late-Gothic two-storey hall of about 3050 m³ with a
mid-frequency reverberation time of about 4.6 s (data set README). The
deposit holds 46 B-format responses (48 kHz; three source positions, S1 with
22 receivers, S2 and S3 with 12 each), the authors' ISO 3382-1 parameters in
29 one-third-octave bands per source (`Nikolauskapelle_Source{1,2,3}_Results_20260205.xlsx`)
and a two-slope DecayFitNet analysis (Götz et al. 2022, methodology [27]) in
the 63, 125, 250 and 500 Hz octave bands (`decayfitnet_all_positions.csv`).

The raw data set is **not** in this repository. Two files derived from it
are, under the same licence and with the attribution in their first line:

* [`aachen-nikolauskapelle-octave.csv`](aachen-nikolauskapelle-octave.csv):
  per position and octave band, ReverbScope's selected slope count, ΔBIC,
  T30, the one-slope T, the forced two-slope T1, T2 and late-energy share,
  the rule that rejected a two-slope fit, whether the `analyze-ir` import
  check accepted the file, and DecayFitNet's T1, T2 and late share (shares
  recomputed as `100·A2/(A1+A2)` from the published `A1`, `A2`).
* [`aachen-nikolauskapelle-thirds.csv`](aachen-nikolauskapelle-thirds.csv):
  per one-third-octave band, written by the script's `--thirds-summary`:
  for EDT, T20 and T30 the median, quartiles and range of the relative
  difference from the authors' values; the number of positions whose slope
  fit chose one or two slopes (or had no VALID fit); and, for the thirds
  inside 63–500 Hz, the same statistics for ReverbScope's decay times
  relative to DecayFitNet's octave-band T1 and T2.

Changes made to the data: only the W (omnidirectional) channel is used; the
DecayFitNet and ISO values are copied for comparison, not altered.

## Method

Run with `scripts/validate_aachen_nikolauskapelle.py --data <folder> --cache
<folder> --out <csv> --thirds-summary <csv>` (the cache makes the run
resumable; each position takes about 2 s on the Linux aarch64 test
machine). Version: this branch, ReverbScope 0.5.0b6 plus the
multi-slope fit and its one-third-octave path.

* **Input.** Channel 1 (W) of each `S*-Do_R*.wav`, all 46 files. The
  excitation range is declared as 20 Hz–20 kHz (the sweep is not in the
  deposit). Time zero is the strongest sample, which is what the import path
  uses.
* **Octave bands, 63 Hz–8 kHz.** `core.decay.analyze_decay`, the analysis
  `reverbscope analyze-ir` runs, with its default settings. This gives T30
  and the multi-slope fit compared with DecayFitNet.
* **One-third-octave bands, 50 Hz–10 kHz.** The product's opt-in
  one-third-octave path, `core.decay.analyze_third_octave_decay` (what
  `--third-octave` adds to `analyze-ir`), on IEC 61260-1 one-third-octave
  filters: EDT, T20 and T30 compared with the authors' values, and the
  slope fit of every third. (Before this path existed the script ran the
  same per-band analysis itself; the EDT/T20/T30 statistics are unchanged
  by the switch, within 0.05 percentage points from the rounding of the
  earlier summary.)
* **Comparison.** Relative difference `100·(ReverbScope / reference − 1)`.
  Only values ReverbScope marks VALID are compared; medians and
  interquartile ranges (IQR, 25th–75th percentile) over positions.

## Results

### EDT, T20 and T30 against the authors' ISO 3382-1 values

Median [IQR] of the relative difference, one-third-octave bands, VALID values
only; `n` is the number of positions compared. Of 1 104 band values per
parameter, 1 084 EDT, 1 090 T20 and 1 081 T30 values were VALID; the rest were
marked unreliable (20, 14, 14) or, for T30, insufficient decay range (9),
mostly at 50 Hz.

| Band | n | EDT | T20 | T30 |
| --- | --- | --- | --- | --- |
| 50 Hz | 39 | −14.5 % [−22.7, +4.5] | +0.6 % [−0.5, +1.1] | +0.3 % [−0.2, +0.7] |
| 63 Hz | 44 | −4.3 % [−9.2, +1.7] | +0.3 % [−0.1, +0.9] | +0.6 % [+0.3, +1.2] |
| 80 Hz | 45 | −2.2 % [−7.0, +6.2] | +0.2 % [−0.3, +0.6] | +0.2 % [−0.1, +0.5] |
| 100 Hz | 45 | −0.1 % [−3.0, +4.0] | +0.1 % [−0.1, +0.3] | +0.3 % [+0.0, +0.7] |
| 125 Hz | 46 | +1.5 % [−3.0, +4.5] | +0.2 % [−0.0, +0.4] | +0.2 % [+0.1, +0.6] |
| 160 Hz | 46 | +1.7 % [−0.3, +4.3] | +0.2 % [−0.0, +0.4] | +0.4 % [+0.2, +0.9] |
| 200 Hz | 46 | +0.8 % [−1.5, +3.0] | +0.2 % [+0.1, +0.4] | +0.6 % [+0.4, +0.9] |
| 250 Hz | 46 | +0.2 % [−1.3, +1.9] | +0.2 % [+0.1, +0.4] | +0.7 % [+0.4, +1.5] |
| 315 Hz | 46 | +0.3 % [−0.6, +1.6] | +0.1 % [+0.0, +0.3] | +0.4 % [+0.2, +1.1] |
| 400 Hz | 45 | +0.5 % [−0.5, +1.1] | +0.1 % [+0.1, +0.3] | +0.4 % [+0.2, +1.0] |
| 500 Hz | 46 | +0.4 % [−0.3, +1.0] | +0.1 % [+0.0, +0.2] | +0.3 % [+0.2, +0.7] |
| 630 Hz | 46 | +0.2 % [−0.8, +0.9] | +0.1 % [+0.0, +0.3] | +0.3 % [+0.1, +0.8] |
| 800 Hz | 46 | +0.2 % [−1.1, +0.4] | +0.0 % [+0.0, +0.1] | +0.2 % [+0.1, +0.5] |
| 1 kHz | 46 | +0.1 % [−1.1, +0.6] | +0.0 % [+0.0, +0.1] | +0.1 % [+0.0, +0.3] |
| 1.25 kHz | 46 | +0.2 % [−1.3, +0.5] | +0.0 % [−0.0, +0.0] | +0.0 % [+0.0, +0.1] |
| 1.6 kHz | 46 | +0.2 % [−0.9, +0.5] | +0.0 % [−0.0, +0.0] | +0.0 % [+0.0, +0.2] |
| 2 kHz | 46 | +0.2 % [−1.5, +0.4] | +0.0 % [+0.0, +0.0] | +0.0 % [+0.0, +0.1] |
| 2.5 kHz | 46 | +0.1 % [−2.1, +0.3] | +0.0 % [−0.0, +0.0] | +0.0 % [+0.0, +0.1] |
| 3.15 kHz | 46 | +0.1 % [−2.0, +0.3] | +0.0 % [−0.0, +0.0] | +0.0 % [+0.0, +0.0] |
| 4 kHz | 46 | −0.0 % [−1.8, +0.1] | +0.0 % [−0.0, +0.0] | +0.0 % [+0.0, +0.1] |
| 5 kHz | 46 | −0.2 % [−2.7, +0.1] | −0.0 % [−0.0, +0.0] | +0.0 % [+0.0, +0.1] |
| 6.3 kHz | 46 | −0.2 % [−1.8, +0.1] | −0.0 % [−0.0, +0.0] | +0.0 % [−0.0, +0.0] |
| 8 kHz | 46 | −0.1 % [−3.9, +0.6] | +0.0 % [−0.0, +0.0] | +0.0 % [+0.0, +0.0] |
| 10 kHz | 46 | −0.4 % [−6.2, +0.2] | +0.0 % [+0.0, +0.0] | +0.0 % [+0.0, +0.1] |

From 100 Hz to 5 kHz, the median absolute difference is 0.07 % for T20
(99.9 % of values within 5 %, the usual just-noticeable difference of
reverberation time), 0.18 % for T30 (99.4 % within 5 %) and 1.1 % for EDT
(88 % within 5 %). EDT depends on the first 10 dB of the decay and so on where
time zero and the direct sound are placed; below 100 Hz, where the source
was a subwoofer and the band filters ring longest, EDT differs systematically
(−14.5 % median at 50 Hz). The authors' software and its onset rule were not
checked; the EDT difference is reported, not explained.

### Slope count against DecayFitNet

Octave bands, 46 positions. DecayFitNet's file gives two slopes for every
position and band; agreement with it is therefore the "2 slopes" column.

| Band | 1 slope | 2 slopes | not VALID or no fit |
| --- | --- | --- | --- |
| 63 Hz | 42 | 4 | 0 |
| 125 Hz | 44 | 2 | 0 |
| 250 Hz | 45 | 1 | 0 |
| 500 Hz | 42 | 4 | 0 |
| 1 kHz | 42 | 4 | 0 |
| 2 kHz | 39 | 7 | 0 |
| 4 kHz | 36 | 10 | 0 |
| 8 kHz | 24 | 22 | 0 |

In the four DecayFitNet bands (63–500 Hz) ReverbScope chose two slopes in
2–9 % of positions (11 of 184 band values). ΔBIC reached the threshold of 10
in 49 of the 180 paired band values; in 38 of those the two-slope fit was
rejected by a plausibility rule. Across all eight octave bands, the 71
rejections were: the single slope already fits within 1 dB (28), the turning
point is less than 10 dB above the noise term (22), the turning point is less
than 10 dB below the fit start, so the fast part is the early decay (10), the
slow slope decays less than 10 dB before the noise (10), and the slopes are
not distinct (1).

DecayFitNet's own two slopes are often close: the median T2/T1 is 1.50,
1.26, 1.32 and 1.16 at 63, 125, 250 and 500 Hz, and T2 ≥ 1.25·T1 (ReverbScope's
distinctness rule) holds for 39, 24, 27 and 15 of 45 positions. The median
late-energy share in DecayFitNet's fits is 8–13 %.

### Slope count in one-third-octave bands

The product's one-third-octave path, 46 positions, 24 bands. DecayFitNet
has no one-third-octave results, so this table has no reference column.

| Band | 1 slope | 2 slopes | not VALID or no fit |
| --- | --- | --- | --- |
| 50 Hz | 34 | 12 | 0 |
| 63 Hz | 40 | 6 | 0 |
| 80 Hz | 44 | 2 | 0 |
| 100 Hz | 45 | 1 | 0 |
| 125 Hz | 43 | 3 | 0 |
| 160 Hz | 45 | 0 | 1 |
| 200 Hz | 45 | 1 | 0 |
| 250 Hz | 44 | 2 | 0 |
| 315 Hz | 43 | 3 | 0 |
| 400 Hz | 44 | 2 | 0 |
| 500 Hz | 43 | 3 | 0 |
| 630 Hz | 42 | 4 | 0 |
| 800 Hz–1.6 kHz (each) | 43 | 3 | 0 |
| 2 kHz | 42 | 4 | 0 |
| 2.5 kHz | 42 | 4 | 0 |
| 3.15 kHz | 43 | 3 | 0 |
| 4 kHz | 41 | 5 | 0 |
| 5 kHz | 45 | 1 | 0 |
| 6.3 kHz | 45 | 1 | 0 |
| 8 kHz | 43 | 3 | 0 |
| 10 kHz | 41 | 5 | 0 |

Two slopes in 77 of 1 103 band values with a VALID fit (7.0 %; 1 of the
1 104 had none). From 80 Hz up the rate is 0–11 % per band (0–5 of 46),
close to the octave bands from 63 Hz to 1 kHz (1–4 of 46); it rises at 63 Hz (6 of 46) and 50 Hz (12 of 46),
inside the 63 Hz octave, where DecayFitNet's two slopes are the most
distinct (median T2/T1 1.50, see below). At 8 kHz the one-third-octave
band chose two slopes 3 times where the 8 kHz octave chose 22. The octave
spans 5.6–11.2 kHz, and one possible reason is that its curve sums thirds
with different decay times (air absorption grows quickly with frequency
there), which a single third does not; this was not checked.

Per position, the octave band and the thirds inside it (VALID octave fits;
"a third 2" means at least one of its three thirds chose two slopes):

| Octave | both 1 slope | octave 1, a third 2 | octave 2, thirds 1 | both 2 |
| --- | --- | --- | --- | --- |
| 63 Hz | 29 | 13 | 1 | 3 |
| 125 Hz | 41 | 3 | 1 | 1 |
| 250 Hz | 39 | 6 | 1 | 0 |
| 500 Hz | 41 | 1 | 0 | 4 |

### One-third-octave slope fit against DecayFitNet's octave values

DecayFitNet's results are octave bands, so each one-third-octave band is
compared with the octave it lies in (50, 63 and 80 Hz with the 63 Hz
octave, and so on). This is **not like for like**: an octave curve is the
sum of its three thirds, each with its own decay times. Median [IQR] of the
relative difference, 45 paired positions (the "1 slope" columns use only
the positions where the third chose one slope):

| Third | DFN octave | RS 2 slopes | RS T (1 slope) vs DFN T1 | RS T (1 slope) vs DFN T2 | forced T1 vs DFN T1 | forced T2 vs DFN T2 | degenerate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 50 Hz | 63 Hz | 11 | +3.8 % [−5.7, +18.6] | −26.3 % [−38.2, −18.4] | −25.4 % [−54.1, −9.5] | −2.9 % [−13.7, +247.9] | 22 |
| 63 Hz | 63 Hz | 6 | +7.3 % [+1.4, +15.8] | −26.4 % [−33.7, −21.5] | −7.3 % [−61.3, +5.9] | −6.0 % [−19.4, +134.0] | 23 |
| 80 Hz | 63 Hz | 2 | +30.5 % [+19.6, +40.8] | −11.9 % [−21.3, −4.3] | +3.7 % [−38.0, +20.0] | +10.1 % [−1.3, +133.9] | 20 |
| 100 Hz | 125 Hz | 1 | +6.4 % [+3.1, +13.3] | −14.3 % [−26.2, −8.4] | −6.4 % [−63.5, +4.0] | +12.9 % [−5.7, +251.1] | 24 |
| 125 Hz | 125 Hz | 3 | +7.5 % [+2.7, +14.5] | −14.5 % [−18.9, −6.9] | −4.8 % [−69.6, +6.5] | −0.4 % [−9.2, +339.5] | 23 |
| 160 Hz | 125 Hz | 1 | +11.7 % [+6.9, +17.3] | −10.8 % [−21.2, −4.5] | +0.5 % [−45.8, +9.5] | +6.9 % [−2.9, +307.1] | 26 |
| 200 Hz | 250 Hz | 1 | +10.3 % [+5.9, +16.4] | −15.4 % [−20.4, −7.1] | +5.0 % [−43.0, +8.7] | +100.7 % [−6.7, +389.9] | 32 |
| 250 Hz | 250 Hz | 1 | +7.6 % [+5.6, +11.7] | −16.5 % [−20.2, −8.7] | +3.6 % [−54.0, +7.3] | +38.4 % [−7.2, +387.0] | 30 |
| 315 Hz | 250 Hz | 3 | +9.5 % [+6.5, +15.6] | −14.2 % [−20.0, −9.7] | +2.3 % [−45.8, +9.2] | +38.1 % [−10.2, +372.7] | 29 |
| 400 Hz | 500 Hz | 2 | +7.0 % [+3.7, +12.3] | −8.9 % [−16.5, −1.4] | −7.1 % [−59.9, +3.3] | +8.7 % [−5.7, +209.9] | 25 |
| 500 Hz | 500 Hz | 3 | +7.3 % [+4.4, +10.5] | −8.0 % [−16.0, −3.2] | +3.1 % [−27.8, +7.0] | −1.1 % [−5.6, +304.8] | 33 |
| 630 Hz | 500 Hz | 4 | +6.0 % [+3.7, +9.9] | −9.2 % [−12.0, −3.9] | +2.0 % [−69.8, +6.6] | +4.4 % [−6.9, +313.1] | 33 |

As in octave bands, where a third chose one slope its decay time lies
between DecayFitNet's octave T1 and T2 in the median of every band (from
+3.8 % above T1 at 50 Hz to +30.5 % at 80 Hz, the upper edge of the 63 Hz
octave). The centre thirds (63, 125, 250 and 500 Hz) sit +7.3 to +7.6 %
above DFN T1, against +6.6 to +21.3 % for ReverbScope's octave bands. The
forced two-slope fits are degenerate in 20 to 33 of 45 positions per third
(18 to 32 in octaves), so their T1 and T2 spreads are wide, as in octave
bands.

### ReverbScope's single slope against DecayFitNet's T1 and T2

Where ReverbScope selected one slope, its decay time against DecayFitNet's
two (median [IQR], 45 positions with a DecayFitNet row minus those with two
slopes selected):

| Band | RS T vs DFN T1 | RS T vs DFN T2 |
| --- | --- | --- |
| 63 Hz | +21.3 % [+14.9, +30.2] | −17.3 % [−25.0, −10.7] |
| 125 Hz | +9.4 % [+4.3, +15.4] | −13.1 % [−20.9, −6.4] |
| 250 Hz | +10.0 % [+5.6, +14.5] | −16.1 % [−20.4, −8.6] |
| 500 Hz | +6.6 % [+3.2, +9.8] | −7.9 % [−12.6, −3.8] |

The single slope lies between DecayFitNet's T1 and T2 in every band, as a
one-exponential fit to a slightly curved decay should. It agrees with
ReverbScope's own T30 to within 2 % (median +1.7 % at 63 Hz, within ±0.5 %
above).

### Forced two-slope fit against DecayFitNet

ReverbScope stores the two-slope model of every band even when it selects
one slope. Its T1 and T2 against DecayFitNet's, all 45 paired positions
(median [IQR]); "degenerate" counts two-slope fits that do not describe two
slopes (T2 < 1.05·T1, T2 above 15 s at the fit bound, or a late share below
1 % or above 99 %):

| Band | T1 vs DFN T1 | T2 vs DFN T2 | late share RS / DFN (median) | degenerate |
| --- | --- | --- | --- | --- |
| 63 Hz | −0.3 % [−44.5, +13.2] | +1.5 % [−8.1, +42.1] | 8.3 % / 8.4 % | 18 of 45 |
| 125 Hz | −0.0 % [−61.6, +5.6] | −1.1 % [−7.5, +143.8] | 6.8 % / 12.5 % | 21 of 45 |
| 250 Hz | +3.2 % [−52.5, +9.6] | +29.2 % [−4.6, +287.4] | 1.0 % / 11.7 % | 28 of 45 |
| 500 Hz | +1.2 % [−55.2, +6.9] | −1.5 % [−6.1, +174.9] | 53.5 % / 13.4 % | 32 of 45 |

The medians agree closely at 63 and 125 Hz, but the spread is wide and from
40 % (63 Hz) to 71 % (500 Hz) of the forced fits are degenerate: on these
curves the second slope is weakly determined, and ReverbScope's least-squares
fit and DecayFitNet's network settle on different pairs. That is the case the
model selection is there for: ReverbScope reports one slope where the data
do not support two by its criteria.

## Limits

* **Import check.** `reverbscope analyze-ir` refuses 16 of the 46 files
  (S1-Do_R16, R19, R21; S2-Do_R3; S3-Do_R1 to R12): their strongest sample is
  less than 10 dB above the content before it (7.9 dB for S3-Do_R1, whose
  peak is 79 ms into the file), so the import path will not take it as the
  direct sound. The script records the refusal and analyses these files with
  the same decay analysis anyway, time zero at the strongest sample. Their
  T30 differences from the authors' values match the others (median +0.17 %
  against +0.13 %; 95th percentile of the absolute difference 2.2 % against
  1.9 %); their EDT median is −3.2 % against +0.4 %, consistent with a
  less certain time zero. A user importing these files would get the
  refusal, not these numbers.
* **One-third-octave slope fit has no like-for-like reference.**
  DecayFitNet's results are octave bands; the one-third-octave slope fit
  (the opt-in `--third-octave` path) is compared with the octave each third
  lies in, which shows how the two differ, not an error of either.
* **Thresholds calibrated on synthetic decays.** ΔBIC ≥ 10, the 10 dB knee
  and noise margins and the 1.25 T2/T1 ratio were chosen on the synthetic
  Monte Carlo of methodology §3c, before this run, and were not tuned to
  this data set. A lower threshold would agree with DecayFitNet more often;
  whether it should is an open decision, not a result.
* **One position missing from DecayFitNet.** The DecayFitNet file covers 45
  positions: S1-Do_R23, the repeat of S1-Do_R22, has no row. It is in the
  ISO and slope-count tables and absent from the paired tables.
* **No ground truth.** Neither DecayFitNet nor ReverbScope is a reference
  for the number of slopes; the comparison shows how the two methods differ
  on the same curves, not which is right. The ISO parameters are the
  authors' published values, not an independent measurement.
* **Channel.** Only the W channel; W is scaled by 1/√2 in the FuMa files,
  which does not change decay times.
