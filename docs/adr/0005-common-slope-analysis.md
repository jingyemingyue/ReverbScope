# Common slopes: one set of decay times for all positions of a room

This decision follows GUIDELINES.zh-CN.md §3 D11 (a core change gets its own
ADR), §4 C1/C2/C12/C16 and docs/API_STABILITY.md. It builds on
[ADR 0004](0004-multi-slope-decay-fit.md).
Status: proposed for maintainer review on `feat/common-slope` (stacked on
`feat/double-slope-fit`).

## Problem

ADR 0004 fits one or two slopes to *each* response. In a coupled room the
second slope is often weak at most positions and strong at a few; fitted one
response at a time it is found at the few and missed (or mis-estimated) at
the others, and every position reports slightly different decay times for
what is one room. The common-slope model (Götz, Schlecht & Pulkki 2023)
describes all positions with the same decay times and position-dependent
amplitudes. ReverbScope already groups positions of one room in a project
(`project.json`, `reverbscope project`, the desktop Project page), but had no
analysis across them except the ISO 3382-2 spatial average of T values.

## Decision

- Add `core/common_slope.py` (NumPy/SciPy only, no new dependency): per
  band, a joint fit of `K` = 1–3 common decay times to the EDCs of all
  positions (k-means start values from the per-response fits as in Götz et
  al.; variable-projection least squares of the dB error), the number of
  slopes by a pooled BIC plus plausibility rules, and per-position
  amplitudes and noise (methodology §3d).
- **Amplitudes: maximum likelihood (LINEX).** Bai & Schlecht (DAFx25) found
  the LINEX regression the most efficient amplitude estimator, the EDC fit
  close but slightly biased. ReverbScope reports the ML amplitudes on the
  band envelope (the Itakura–Saito form of the same likelihood) and keeps
  the EDC-fit amplitudes as `--amplitudes edc`.
- **IS-NMF / SAGE (arXiv:2610.05549) is implemented, opt-in and marked
  experimental** (`--estimator is-sage`): the paper validates on synthetic
  data only; ReverbScope reproduces its synthetic behaviour in the unit tests
  but has no ground truth for measured rooms. The EDC estimate stays the
  default, and SAGE's result keeps the EDC decay times beside it. SAGE uses
  the `K` selected by the EDC fit (the paper prescribes `K`).
- **Entry points.** A new command, `reverbscope common-slope INPUT...`,
  accepts IR WAVs (with `--band`, like `analyze-ir`), session folders and
  project folders (each listed position), prints a table and with `--out`
  writes `common-slope.json` and two CSV files. Because a multi-position
  concept already exists in the desktop app, its Project page gets a
  *Common slopes* card that runs the analysis on request in a worker thread
  and shows the per-band table; amplitudes are exported through the CLI.
- **Additive only.** A new file kind with its own schema
  (`common-slope.schema.json`, `reverbscope schema common-slope`, version 1);
  `result.json`, `session.json`, `project.json` and every single-response
  number, report and CSV are unchanged (nothing is stored in a session).
- **Thresholds.** `ΔBIC ≥ 10`, the 1.25× ratio and the 10 dB spans are ADR
  0004's. Two rules are new and ReverbScope's choice: every slope must be
  supported (largest term above the noise over 10 dB of decay) at two
  positions or more and at least 5 % of them, and the extra slope must
  halve the RMS error at one position or more. Calibrated on synthetic rooms
  (`tests/unit/test_common_slope.py`) and checked on the Aachen data.

## Evidence and limits

Synthetic tests (shared decay times with varying amplitudes and noise, order
selection, degenerate inputs, the SAGE setting of the paper), CLI and GUI
tests, and the open Aachen St. Nicholas Chapel data
([validation/aachen-nikolauskapelle-common-slope.md](../validation/aachen-nikolauskapelle-common-slope.md)).
Not a standard method; no ISO tolerance. The amplitude and SAGE estimators
are validated on synthetic data only. The analysis reads the impulse
responses again (about 1 s per response for octave bands at 48 kHz, 10 s
long), so it runs on request, not with every project load. The Aachen run is
third-party measured data analysed offline; it is not a ReverbScope
hardware or DAW test (C16).

## Alternatives not taken

- *k-means only* (Götz et al.'s procedure without the joint refinement): the
  cluster centres of per-response fits inherit their bias towards the
  dominant slope; refining them jointly lets weak-slope positions count.
- *DecayFitNet* for the per-response estimates: PyTorch and model weights
  are a dependency ADR 0004 already declined.
- *SAGE as default*: no measured-data validation yet; its result depends on
  the early part of the envelope that the EDC fit starts after.
- *Storing common slopes in `project.json`*: a derived result that changes
  with the analysis version; it is exported, not stored.
