# Validation campaign (M11)

Status: **protocol written; not yet run.** ARCHITECTURE_V1.md §7.4 requires
real-room evidence before 1.0. This file is that protocol. A campaign that
fails its tolerances still gets published; it blocks 1.0 until the
disagreements are explained or turned into issues.

Nothing below is filled from the fake backend, from synthetic tests, or from
memory of a measurement that is not attached.

## 1. Purpose

The synthetic suite proves the algebra against published sources. This
campaign asks whether the same numbers appear on a real recording, and
whether the placement figures match a tape measure. The same WAV is analysed
by ReverbScope and by a reference instrument so that acquisition is isolated
from analysis.

## 2. Pre-chosen acceptance tolerances

These tolerances were written **before** any campaign recording. They are
ReverbScope's engineering gates for 1.0, not a claim that a purchased copy of
ISO 3382-2 was used to verify Table values.

| Comparison | Quantity | Tolerance | Why this number |
| --- | --- | --- | --- |
| Same WAV, ReverbScope vs reference instrument | T20, T30 per overlapping octave band that both tools mark usable | 5 % or 0.02 s, whichever is larger | ISO 3382-1 just-noticeable difference for reverberation time is 5 % |
| Same WAV, ReverbScope vs reference instrument | EDT per overlapping usable band | 10 % or 0.03 s, whichever is larger | EDT uses a short early range and moves more |
| Same WAV, ReverbScope vs reference instrument | Delay of the strongest early reflection after the direct sound | 0.2 ms | One analysis hop at 48 kHz is ~0.02 ms; 0.2 ms is ten samples and above the detector's 0.1 ms peak-hold |
| Same WAV, ReverbScope vs reference instrument | Loopback-compensated frequency response, median in the excitation normalisation band | 1.0 dB | Same acceptance already used for a synthetic interface FIR (`LOOPBACK_FR_ACCEPTANCE_DB`) |
| Tape vs ReverbScope | `source_height_m`, `ceiling_height_m` when both are VALID | 5 cm | Same bound as the synthetic whole-chain placement test |
| Repeatability | Two successive takes at one position without moving anything | T20/T30 within 5 % or 0.02 s | Same JND; flags a stand or a clock problem before the reference comparison |

A band that either tool marks unusable (`insufficient_decay_range`,
outside the excitation, or the reference's equivalent) is excluded from the
T comparison and listed, not forced into a percentage.

## 3. Rooms and positions

Minimum for 1.0:

* two rooms: one treated (booth / treated control room), one untreated
  (live room / ordinary room);
* at least two microphone positions in each room;
* one loudspeaker position per room (ReverbScope is a single-source tool);
* one interface, one loudspeaker, one measurement microphone, used for
  every take.

Record the make/model of every device, the sample rate, the buffer size,
and whether a loopback cable was used. Photograph the two positions with
the tape in frame.

## 4. Reference instrument

Allowed comparison instruments (ARCHITECTURE_V1.md §13):

* Room EQ Wizard, used only as a comparison instrument. Do not copy REW
  source, do not reverse engineer it, do not redistribute it.
* An open MATLAB / Python toolbox with a clear license, named in the
  results table.

The maintainer decides which one is used. The protocol is the same either
way: export the **same recorded WAV** (and the same sweep definition) into
both tools.

## 5. Procedure

1. Generate the ReverbScope sweep at the interface rate. Keep the
   `.reverbscope-sweep.json` sidecar.
2. Set monitor level low. Acknowledge −12 dBFS on every take; never persist
   that acknowledgement.
3. Universal DAW Mode or Standalone Mode is acceptable. Prefer a loopback
   channel on at least one take per room.
4. Measure the loudspeaker-to-capsule distance and the microphone height
   with a tape. Write the numbers on paper *before* looking at ReverbScope's
   placement tab. Air temperature if a thermometer is available.
5. Record two takes at position A without moving anything (repeatability),
   then position B.
6. Bounce the recording without trimming.
7. Analyse in ReverbScope (`reverbscope analyze` or the GUI) with the tape
   numbers entered. Save the session folder.
8. Analyse the same WAV in the reference instrument with the same
   excitation band and, where the tool allows it, the same evaluation
   ranges (−5 to −25 dB for T20, −5 to −35 dB for T30).
9. Fill the results table. Every disagreement that exceeds a tolerance
   becomes an issue or an explained row. Unexplained failures block 1.0.

## 6. Results table (empty until the campaign runs)

| Room | Position | Take | Metric | ReverbScope | Reference / tape | Delta | Gate | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | | |

Attach for every row that is filled: the session bundle (prefer
`--no-audio` plus a separate CC0 WAV if the recording may be published),
`SHA256` of the WAV, the ReverbScope version, and the reference-instrument
version.

Raw files that are too large for the repository go on the GitHub Release
of the campaign as CC0 assets with checksums.

## 7. Maintainer decisions this campaign still needs

From ARCHITECTURE_V1.md §13: which reference instrument, which two rooms,
who runs it, and whether REW is the comparison instrument. This protocol
does not make those decisions.

## 8. What this file is not

It is not evidence that any real room was measured. The synthetic suite
remains the only evidence that the algorithms match their published
sources until §6 has dated rows.
